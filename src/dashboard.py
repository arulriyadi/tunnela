import logging
import random, shutil, sqlite3, configparser, hashlib, ipaddress, json, os, secrets, socket, stat, subprocess, shlex
import time, re, uuid, bcrypt, psutil, pyotp, threading
import traceback
from uuid import uuid4
from zipfile import ZipFile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, available_timezones

import sqlalchemy
from jinja2 import Template
from flask import Flask, request, render_template, session, send_file
from flask_cors import CORS
from icmplib import ping, traceroute
from flask.json.provider import DefaultJSONProvider
from itertools import islice

from sqlalchemy import RowMapping

from modules.Utilities import (
    RegexMatch, StringToBoolean,
    ValidateIPAddressesWithRange, ValidateDNSAddress,
    GenerateWireguardPublicKey, GenerateWireguardPrivateKey
)
from packaging import version
from modules.Email import EmailSender
from modules.DashboardLogger import DashboardLogger
from modules.PeerJob import PeerJob
from modules.SystemStatus import SystemStatus
from modules.PeerShareLinks import PeerShareLinks
from modules.PeerJobs import PeerJobs
from modules.DashboardConfig import DashboardConfig
from modules.WireguardConfiguration import WireguardConfiguration
from modules.AmneziaWireguardConfiguration import AmneziaWireguardConfiguration

from client import createClientBlueprint

from logging.config import dictConfig

from modules.DashboardClients import DashboardClients
from modules.ClientsNetworkOverviewStats import ClientsNetworkOverviewStats
from modules.ClientsNetworkOverviewScheduler import (
    start_clients_network_overview_scheduler as _start_clients_network_overview_scheduler,
    reschedule_clients_network_overview_job,
)
from modules.DashboardPlugins import DashboardPlugins
from modules.DashboardWebHooks import DashboardWebHooks
from modules.NewConfigurationTemplates import NewConfigurationTemplates

class CustomJsonEncoder(DefaultJSONProvider):
    def __init__(self, app):
        super().__init__(app)

    def default(self, o):
        if callable(getattr(o, "toJson", None)):
            return o.toJson()
        if type(o) is RowMapping:
            return dict(o)
        if type(o) is datetime:
            return o.strftime("%Y-%m-%d %H:%M:%S")
        return super().default(self)



'''
Response Object
'''
def ResponseObject(status=True, message=None, data=None, status_code = 200) -> Flask.response_class:
    response = Flask.make_response(app, {
        "status": status,
        "message": message,
        "data": data
    })
    response.status_code = status_code
    response.content_type = "application/json"
    return response

'''
Flask App
'''
app = Flask("WGDashboard", template_folder=os.path.abspath("./static/dist/WGDashboardAdmin"))

def peerInformationBackgroundThread():
    global WireguardConfigurations
    app.logger.info("Background Thread #1 Started")
    app.logger.info("Background Thread #1 PID:" + str(threading.get_native_id()))
    delay = 6
    time.sleep(10)
    while True:
        with app.app_context():
            try:
                curKeys = list(WireguardConfigurations.keys())
                for name in curKeys:
                    if name in WireguardConfigurations.keys() and WireguardConfigurations.get(name) is not None:
                        c = WireguardConfigurations.get(name)
                        if c.getStatus():
                            c.getPeersLatestHandshake()
                            c.getPeersTransfer()
                            c.getPeersEndpoint()
                            c.getPeers()
                            if delay == 6:
                                if c.configurationInfo.PeerTrafficTracking:
                                    c.logPeersTraffic()
                                if c.configurationInfo.PeerHistoricalEndpointTracking:
                                    c.logPeersHistoryEndpoint()
                            c.getRestrictedPeersList()
            except Exception as e:
                app.logger.error(f"[WGDashboard] Background Thread #1 Error", e)

        if delay == 6:
            delay = 1
        else:
            delay += 1
        time.sleep(10)

def peerJobScheduleBackgroundThread():
    with app.app_context():
        app.logger.info(f"Background Thread #2 Started")
        app.logger.info(f"Background Thread #2 PID:" + str(threading.get_native_id()))
        time.sleep(10)
        while True:
            try:
                AllPeerJobs.runJob()
                time.sleep(180)
            except Exception as e:
                app.logger.error("Background Thread #2 Error", e)

def _ensure_gunicorn_socket_parent_dir(absolute_socket_path: str) -> None:
    """Create parent directory for the Unix socket (idempotent). Typical default: {CONFIGURATION_PATH}/run/."""
    parent = os.path.dirname(absolute_socket_path)
    if parent:
        os.makedirs(parent, mode=0o755, exist_ok=True)


def gunicornConfig() -> tuple[str, str]:
    """
    Gunicorn bind settings from wg-dashboard.ini [Server].

    Returns (bind, app_listen_mode) where bind is a Gunicorn bind string:
    host:port for direct TCP, or unix:/path for nginx_socket.
    """
    exist_mode, mode_raw = DashboardConfig.GetConfig("Server", "app_listen_mode")
    mode = (str(mode_raw) if exist_mode and mode_raw is not None else "direct").strip()
    if mode not in ("direct", "nginx_socket"):
        mode = "direct"
    if mode == "nginx_socket":
        exist_sock, sock = DashboardConfig.GetConfig("Server", "gunicorn_socket_path")
        path = (str(sock) if exist_sock and sock is not None else "").strip()
        if not path:
            raise RuntimeError(
                "app_listen_mode is nginx_socket but gunicorn_socket_path is missing or empty"
            )
        _ensure_gunicorn_socket_parent_dir(path)
        return f"unix:{path}", mode
    _, app_ip = DashboardConfig.GetConfig("Server", "app_ip")
    _, app_port = DashboardConfig.GetConfig("Server", "app_port")
    return f"{app_ip}:{app_port}", mode

def ProtocolsEnabled() -> list[str]:
    from shutil import which
    protocols = []
    if which('awg') is not None and which('awg-quick') is not None:
        protocols.append("awg")
    if which('wg') is not None and which('wg-quick') is not None:
        protocols.append("wg")
    return protocols

def InitWireguardConfigurationsList(startup: bool = False):
    if os.path.exists(DashboardConfig.GetConfig("Server", "wg_conf_path")[1]):
        confs = os.listdir(DashboardConfig.GetConfig("Server", "wg_conf_path")[1])
        confs.sort()
        for i in confs:
            if RegexMatch("^(.{1,}).(conf)$", i):
                i = i.replace('.conf', '')
                try:
                    if i in WireguardConfigurations.keys():
                        if WireguardConfigurations[i].configurationFileChanged():
                            with app.app_context():
                                WireguardConfigurations[i] = WireguardConfiguration(DashboardConfig, AllPeerJobs, AllPeerShareLinks, DashboardWebHooks, i)
                    else:
                        with app.app_context():
                            WireguardConfigurations[i] = WireguardConfiguration(DashboardConfig, AllPeerJobs, AllPeerShareLinks, DashboardWebHooks, i, startup=startup)
                except WireguardConfiguration.InvalidConfigurationFileException as e:
                    app.logger.error(f"{i} have an invalid configuration file.")

    if "awg" in ProtocolsEnabled():
        confs = os.listdir(DashboardConfig.GetConfig("Server", "awg_conf_path")[1])
        confs.sort()
        for i in confs:
            if RegexMatch("^(.{1,}).(conf)$", i):
                i = i.replace('.conf', '')
                try:
                    if i in WireguardConfigurations.keys():
                        if WireguardConfigurations[i].configurationFileChanged():
                            with app.app_context():
                                WireguardConfigurations[i] = AmneziaWireguardConfiguration(DashboardConfig, AllPeerJobs, AllPeerShareLinks, DashboardWebHooks, i)
                    else:
                        with app.app_context():
                            WireguardConfigurations[i] = AmneziaWireguardConfiguration(DashboardConfig, AllPeerJobs, AllPeerShareLinks, DashboardWebHooks, i, startup=startup)
                except WireguardConfiguration.InvalidConfigurationFileException as e:
                    app.logger.error(f"{i} have an invalid configuration file.")

def startThreads():
    bgThread = threading.Thread(target=peerInformationBackgroundThread, daemon=True)
    bgThread.start()
    scheduleJobThread = threading.Thread(target=peerJobScheduleBackgroundThread, daemon=True)
    scheduleJobThread.start()


def start_clients_network_overview_scheduler():
    _start_clients_network_overview_scheduler(app)

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] [%(levelname)s] in [%(module)s] %(message)s',
    }},
    'root': {
        'level': 'INFO'
    }
})


WireguardConfigurations: dict[str, WireguardConfiguration] = {}
CONFIGURATION_PATH = os.getenv('CONFIGURATION_PATH', '.')

app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 5206928
app.secret_key = secrets.token_urlsafe(32)
app.json = CustomJsonEncoder(app)
with app.app_context():
    SystemStatus = SystemStatus()
    DashboardConfig = DashboardConfig()
    EmailSender = EmailSender(DashboardConfig)
    AllPeerShareLinks: PeerShareLinks = PeerShareLinks(DashboardConfig, WireguardConfigurations)
    AllPeerJobs: PeerJobs = PeerJobs(DashboardConfig, WireguardConfigurations, AllPeerShareLinks)
    DashboardLogger: DashboardLogger = DashboardLogger()
    DashboardPlugins: DashboardPlugins = DashboardPlugins(app, WireguardConfigurations)
    DashboardWebHooks: DashboardWebHooks = DashboardWebHooks(DashboardConfig)
    NewConfigurationTemplates: NewConfigurationTemplates = NewConfigurationTemplates()
    InitWireguardConfigurationsList(startup=True)
    ClientsNetworkOverviewStatsManager: ClientsNetworkOverviewStats = ClientsNetworkOverviewStats(
        DashboardConfig
    )
    DashboardClients: DashboardClients = DashboardClients(WireguardConfigurations)
    app.register_blueprint(createClientBlueprint(WireguardConfigurations, DashboardConfig, DashboardClients))

_, APP_PREFIX = DashboardConfig.GetConfig("Server", "app_prefix")
cors = CORS(app, resources={rf"{APP_PREFIX}/api/*": {
    "origins": "*",
    "methods": "DELETE, POST, GET, OPTIONS",
    "allow_headers": ["Content-Type", "wg-dashboard-apikey"]
}})
_, app_ip = DashboardConfig.GetConfig("Server", "app_ip")
_, app_port = DashboardConfig.GetConfig("Server", "app_port")
_, WG_CONF_PATH = DashboardConfig.GetConfig("Server", "wg_conf_path")


def resolve_update_github_repo():
    """owner/repo for GitHub releases API; env WGDASHBOARD_UPDATE_GITHUB_REPO overrides ini."""
    import re

    env = os.environ.get("WGDASHBOARD_UPDATE_GITHUB_REPO", "").strip()
    if env:
        repo = env
    else:
        _, repo = DashboardConfig.GetConfig("Server", "update_github_repo")
        repo = (repo or "").strip()
    if not repo or not re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", repo):
        return "WGDashboard/WGDashboard"
    return repo


'''
API Routes
'''

@app.before_request
def auth_req():
    if request.method.lower() == 'options':
        return ResponseObject(True)        

    DashboardConfig.APIAccessed = False    
    authenticationRequired = DashboardConfig.GetConfig("Server", "auth_req")[1]
    d = request.headers
    if authenticationRequired:
        apiKey = d.get('wg-dashboard-apikey')
        apiKeyEnabled = DashboardConfig.GetConfig("Server", "dashboard_api_key")[1]
        if apiKey is not None and len(apiKey) > 0 and apiKeyEnabled:
            apiKeyExist = len(list(filter(lambda x : x.Key == apiKey, DashboardConfig.DashboardAPIKeys))) == 1
            DashboardLogger.log(str(request.url), str(request.remote_addr), Message=f"API Key Access: {('true' if apiKeyExist else 'false')} - Key: {apiKey}")
            if not apiKeyExist:
                DashboardConfig.APIAccessed = False
                response = Flask.make_response(app, {
                    "status": False,
                    "message": "API Key does not exist",
                    "data": None
                })
                response.content_type = "application/json"
                response.status_code = 401
                return response
            DashboardConfig.APIAccessed = True
        else:
            DashboardConfig.APIAccessed = False
            appPrefix = APP_PREFIX if len(APP_PREFIX) > 0 else ''
            whiteList = [
                # f'/static/', 
                f'{appPrefix}/api/validateAuthentication', 
                f'{appPrefix}/api/authenticate', 
                # f'{appPrefix}/api/getDashboardConfiguration',
                f'{appPrefix}/api/getDashboardTheme', 
                f'{appPrefix}/api/getDashboardVersion',
                f'{appPrefix}/api/getLoginFooterSettings',
                f'{appPrefix}/api/sharePeer/get', 
                f'{appPrefix}/api/isTotpEnabled', 
                f'{appPrefix}/api/locale',
            ]
        

            if (    
                    ("username" not in session or session.get("role") != "admin")
                    and (f"{appPrefix}/" != request.path and f"{appPrefix}" != request.path)
                    and not request.path.startswith(f'{appPrefix}/client')
                    and not request.path.startswith(f'{appPrefix}/static')
                    and request.path not in whiteList
            ):
                response = Flask.make_response(app, {
                    "status": False,
                    "message": "Unauthorized access.",
                    "data": None
                })
                response.content_type = "application/json"
                response.status_code = 401
                return response

@app.route(f'{APP_PREFIX}/api/handshake', methods=["GET", "OPTIONS"])
def API_Handshake():
    return ResponseObject(True)

@app.get(f'{APP_PREFIX}/api/validateAuthentication')
def API_ValidateAuthentication():
    token = request.cookies.get("authToken")
    if DashboardConfig.GetConfig("Server", "auth_req")[1]:
        if token is None or token == "" or "username" not in session or session["username"] != token:
            return ResponseObject(False, "Invalid authentication.")
    return ResponseObject(True)

@app.get(f'{APP_PREFIX}/api/requireAuthentication')
def API_RequireAuthentication():
    return ResponseObject(data=DashboardConfig.GetConfig("Server", "auth_req")[1])

@app.post(f'{APP_PREFIX}/api/authenticate')
def API_AuthenticateLogin():
    data = request.get_json()
    if not DashboardConfig.GetConfig("Server", "auth_req")[1]:
        return ResponseObject(True, DashboardConfig.GetConfig("Other", "welcome_session")[1])
    
    if DashboardConfig.APIAccessed:
        authToken = hashlib.sha256(f"{request.headers.get('wg-dashboard-apikey')}{datetime.now()}".encode()).hexdigest()
        session['role'] = 'admin'
        session['username'] = authToken
        resp = ResponseObject(True, DashboardConfig.GetConfig("Other", "welcome_session")[1])
        resp.set_cookie("authToken", authToken)
        session.permanent = True
        return resp
    valid = bcrypt.checkpw(data['password'].encode("utf-8"),
                           DashboardConfig.GetConfig("Account", "password")[1].encode("utf-8"))
    totpEnabled = DashboardConfig.GetConfig("Account", "enable_totp")[1]
    totpValid = False
    if totpEnabled:
        totpValid = pyotp.TOTP(DashboardConfig.GetConfig("Account", "totp_key")[1]).now() == data['totp']

    if (valid
            and data['username'] == DashboardConfig.GetConfig("Account", "username")[1]
            and ((totpEnabled and totpValid) or not totpEnabled)
    ):
        authToken = hashlib.sha256(f"{data['username']}{datetime.now()}".encode()).hexdigest()
        session['role'] = 'admin'
        session['username'] = authToken
        resp = ResponseObject(True, DashboardConfig.GetConfig("Other", "welcome_session")[1])
        resp.set_cookie("authToken", authToken)
        session.permanent = True
        DashboardLogger.log(str(request.url), str(request.remote_addr), Message=f"Login success: {data['username']}")
        return resp
    DashboardLogger.log(str(request.url), str(request.remote_addr), Message=f"Login failed: {data['username']}")
    if totpEnabled:
        return ResponseObject(False, "Sorry, your username, password or OTP is incorrect.")
    else:
        return ResponseObject(False, "Sorry, your username or password is incorrect.")

@app.get(f'{APP_PREFIX}/api/signout')
def API_SignOut():
    resp = ResponseObject(True, "")
    resp.delete_cookie("authToken")
    session.clear()
    return resp

@app.get(f'{APP_PREFIX}/api/getWireguardConfigurations')
def API_getWireguardConfigurations():
    InitWireguardConfigurationsList()
    return ResponseObject(data=[wc for wc in WireguardConfigurations.values()])

@app.get(f'{APP_PREFIX}/api/newConfigurationTemplates')
def API_NewConfigurationTemplates():
    return ResponseObject(data=NewConfigurationTemplates.GetTemplates())

@app.get(f'{APP_PREFIX}/api/newConfigurationTemplates/createTemplate')
def API_NewConfigurationTemplates_CreateTemplate():
    return ResponseObject(data=NewConfigurationTemplates.CreateTemplate().model_dump())

@app.post(f'{APP_PREFIX}/api/newConfigurationTemplates/updateTemplate')
def API_NewConfigurationTemplates_UpdateTemplate():
    data = request.get_json()
    template = data.get('Template', None)
    if not template:
        return ResponseObject(False, "Please provide template")
    
    status, msg = NewConfigurationTemplates.UpdateTemplate(template)
    return ResponseObject(status, msg)

@app.post(f'{APP_PREFIX}/api/newConfigurationTemplates/deleteTemplate')
def API_NewConfigurationTemplates_DeleteTemplate():
    data = request.get_json()
    template = data.get('Template', None)
    if not template:
        return ResponseObject(False, "Please provide template")

    status, msg = NewConfigurationTemplates.DeleteTemplate(template)
    return ResponseObject(status, msg)

@app.post(f'{APP_PREFIX}/api/addWireguardConfiguration')
def API_addWireguardConfiguration():
    data = request.get_json()
    requiredKeys = [
        "ConfigurationName", "Address", "ListenPort", "PrivateKey", "Protocol"
    ]
    for i in requiredKeys:
        if i not in data.keys():
            return ResponseObject(False, "Please provide all required parameters.")
    
    if data.get("Protocol") not in ProtocolsEnabled():
        return ResponseObject(False, "Please provide a valid protocol: wg / awg.")

    # Check duplicate names, ports, address
    for i in WireguardConfigurations.values():
        if i.Name == data['ConfigurationName']:
            return ResponseObject(False,
                                  f"Already have a configuration with the name \"{data['ConfigurationName']}\"",
                                  "ConfigurationName")

        if str(i.ListenPort) == str(data["ListenPort"]):
            return ResponseObject(False,
                                  f"Already have a configuration with the port \"{data['ListenPort']}\"",
                                  "ListenPort")

        if i.Address == data["Address"]:
            return ResponseObject(False,
                                  f"Already have a configuration with the address \"{data['Address']}\"",
                                  "Address")

    if "Backup" in data.keys():
        path = {
            "wg": DashboardConfig.GetConfig("Server", "wg_conf_path")[1],
            "awg": DashboardConfig.GetConfig("Server", "awg_conf_path")[1]
        }
     
        if (os.path.exists(os.path.join(path['wg'], 'WGDashboard_Backup', data["Backup"])) and
                os.path.exists(os.path.join(path['wg'], 'WGDashboard_Backup', data["Backup"].replace('.conf', '.sql')))):
            protocol = "wg"
        elif (os.path.exists(os.path.join(path['awg'], 'WGDashboard_Backup', data["Backup"])) and
              os.path.exists(os.path.join(path['awg'], 'WGDashboard_Backup', data["Backup"].replace('.conf', '.sql')))):
            protocol = "awg"
        else:
            return ResponseObject(False, "Backup does not exist")
        
        shutil.copy(
            os.path.join(path[protocol], 'WGDashboard_Backup', data["Backup"]),
            os.path.join(path[protocol], f'{data["ConfigurationName"]}.conf')
        )
        WireguardConfigurations[data['ConfigurationName']] = (
            WireguardConfiguration(DashboardConfig, AllPeerJobs, AllPeerShareLinks, data=data, name=data['ConfigurationName'])) if protocol == 'wg' else (
            AmneziaWireguardConfiguration(DashboardConfig, AllPeerJobs, AllPeerShareLinks, DashboardWebHooks, data=data, name=data['ConfigurationName']))
    else:
        WireguardConfigurations[data['ConfigurationName']] = (
            WireguardConfiguration(DashboardConfig, AllPeerJobs, AllPeerShareLinks, DashboardWebHooks, data=data)) if data.get('Protocol') == 'wg' else (
            AmneziaWireguardConfiguration(DashboardConfig, AllPeerJobs, AllPeerShareLinks, DashboardWebHooks, data=data))
    return ResponseObject()

@app.get(f'{APP_PREFIX}/api/toggleWireguardConfiguration')
def API_toggleWireguardConfiguration():
    configurationName = request.args.get('configurationName')
    if configurationName is None or len(
            configurationName) == 0 or configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Please provide a valid configuration name", status_code=404)
    toggleStatus, msg = WireguardConfigurations[configurationName].toggleConfiguration()
    return ResponseObject(toggleStatus, msg, WireguardConfigurations[configurationName].Status)

@app.post(f'{APP_PREFIX}/api/updateWireguardConfiguration')
def API_updateWireguardConfiguration():
    data = request.get_json()
    requiredKeys = ["Name"]
    for i in requiredKeys:
        if i not in data.keys():
            return ResponseObject(False, "Please provide these following field: " + ", ".join(requiredKeys))
    name = data.get("Name")
    if name not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist", status_code=404)
    
    status, msg = WireguardConfigurations[name].updateConfigurationSettings(data)
    
    return ResponseObject(status, message=msg, data=WireguardConfigurations[name])

@app.post(f'{APP_PREFIX}/api/updateWireguardConfigurationInfo')
def API_updateWireguardConfigurationInfo():
    data = request.get_json()
    name = data.get('Name')
    key = data.get('Key')
    value = data.get('Value')
    if not all([data, key, name]):
        return ResponseObject(status=False, message="Please provide configuration name, key and value")
    if name not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist", status_code=404)
    
    status, msg, key = WireguardConfigurations[name].updateConfigurationInfo(key, value)
    
    return ResponseObject(status=status, message=msg, data=key)

@app.get(f'{APP_PREFIX}/api/getWireguardConfigurationRawFile')
def API_GetWireguardConfigurationRawFile():
    configurationName = request.args.get('configurationName')
    if configurationName is None or len(
            configurationName) == 0 or configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Please provide a valid configuration name", status_code=404)
    
    return ResponseObject(data={
        "path": WireguardConfigurations[configurationName].configPath,
        "content": WireguardConfigurations[configurationName].getRawConfigurationFile()
    })

@app.post(f'{APP_PREFIX}/api/updateWireguardConfigurationRawFile')
def API_UpdateWireguardConfigurationRawFile():
    data = request.get_json()
    configurationName = data.get('configurationName')
    rawConfiguration = data.get('rawConfiguration')
    if configurationName is None or len(
            configurationName) == 0 or configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Please provide a valid configuration name")
    if rawConfiguration is None or len(rawConfiguration) == 0:
        return ResponseObject(False, "Please provide content")
    
    status, err = WireguardConfigurations[configurationName].updateRawConfigurationFile(rawConfiguration)

    return ResponseObject(status=status, message=err)

@app.post(f'{APP_PREFIX}/api/deleteWireguardConfiguration')
def API_deleteWireguardConfiguration():
    data = request.get_json()
    if "ConfigurationName" not in data.keys() or data.get("ConfigurationName") is None or data.get("ConfigurationName") not in WireguardConfigurations.keys():
        return ResponseObject(False, "Please provide the configuration name you want to delete", status_code=404)
    rp =  WireguardConfigurations.pop(data.get("ConfigurationName"))
    
    status = rp.deleteConfiguration()
    if not status:
        WireguardConfigurations[data.get("ConfigurationName")] = rp
    return ResponseObject(status)

@app.post(f'{APP_PREFIX}/api/renameWireguardConfiguration')
def API_renameWireguardConfiguration():
    data = request.get_json()
    keys = ["ConfigurationName", "NewConfigurationName"]
    for k in keys:
        if (k not in data.keys() or data.get(k) is None or len(data.get(k)) == 0 or 
                (k == "ConfigurationName" and data.get(k) not in WireguardConfigurations.keys())): 
            return ResponseObject(False, "Please provide the configuration name you want to rename", status_code=404)
    
    if data.get("NewConfigurationName") in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration name already exist", status_code=400)
    
    rc = WireguardConfigurations.pop(data.get("ConfigurationName"))
    
    status, message = rc.renameConfiguration(data.get("NewConfigurationName"))
    if status:
        WireguardConfigurations[data.get("NewConfigurationName")] = (WireguardConfiguration(DashboardConfig, AllPeerJobs, AllPeerShareLinks, DashboardWebHooks, data.get("NewConfigurationName")) if rc.Protocol == 'wg' else AmneziaWireguardConfiguration(DashboardConfig, AllPeerJobs, AllPeerShareLinks, DashboardWebHooks, data.get("NewConfigurationName")))
    else:
        WireguardConfigurations[data.get("ConfigurationName")] = rc
    return ResponseObject(status, message)

@app.get(f'{APP_PREFIX}/api/getWireguardConfigurationRealtimeTraffic')
def API_getWireguardConfigurationRealtimeTraffic():
    configurationName = request.args.get('configurationName')
    if configurationName is None or configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist", status_code=404)
    return ResponseObject(data=WireguardConfigurations[configurationName].getRealtimeTrafficUsage())

@app.get(f'{APP_PREFIX}/api/getWireguardConfigurationBackup')
def API_getWireguardConfigurationBackup():
    configurationName = request.args.get('configurationName')
    if configurationName is None or configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist",  status_code=404)
    return ResponseObject(data=WireguardConfigurations[configurationName].getBackups())

@app.get(f'{APP_PREFIX}/api/getAllWireguardConfigurationBackup')
def API_getAllWireguardConfigurationBackup():
    data = {
        "ExistingConfigurations": {},
        "NonExistingConfigurations": {}
    }
    existingConfiguration = WireguardConfigurations.keys()
    for i in existingConfiguration:
        b = WireguardConfigurations[i].getBackups(True)
        if len(b) > 0:
            data['ExistingConfigurations'][i] = WireguardConfigurations[i].getBackups(True)
            
    for protocol in ProtocolsEnabled():
        directory = os.path.join(DashboardConfig.GetConfig("Server", f"{protocol}_conf_path")[1], 'WGDashboard_Backup')
        if os.path.exists(directory):
            files = [(file, os.path.getctime(os.path.join(directory, file)))
                     for file in os.listdir(directory) if os.path.isfile(os.path.join(directory, file))]
            files.sort(key=lambda x: x[1], reverse=True)
        
            for f, ct in files:
                if RegexMatch(r"^(.*)_(.*)\.(conf)$", f):
                    s = re.search(r"^(.*)_(.*)\.(conf)$", f)
                    name = s.group(1)
                    if name not in existingConfiguration:
                        if name not in data['NonExistingConfigurations'].keys():
                            data['NonExistingConfigurations'][name] = []
                        
                        date = s.group(2)
                        d = {
                            "protocol": protocol,
                            "filename": f,
                            "backupDate": date,
                            "content": open(os.path.join(DashboardConfig.GetConfig("Server", f"{protocol}_conf_path")[1], 'WGDashboard_Backup', f), 'r').read()
                        }
                        if f.replace(".conf", ".sql") in list(os.listdir(directory)):
                            d['database'] = True
                            d['databaseContent'] = open(os.path.join(DashboardConfig.GetConfig("Server", f"{protocol}_conf_path")[1], 'WGDashboard_Backup', f.replace(".conf", ".sql")), 'r').read()
                        data['NonExistingConfigurations'][name].append(d)
    return ResponseObject(data=data)

@app.get(f'{APP_PREFIX}/api/createWireguardConfigurationBackup')
def API_createWireguardConfigurationBackup():
    configurationName = request.args.get('configurationName')
    if configurationName is None or configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist",  status_code=404)
    return ResponseObject(status=WireguardConfigurations[configurationName].backupConfigurationFile()[0], 
                          data=WireguardConfigurations[configurationName].getBackups())

@app.post(f'{APP_PREFIX}/api/deleteWireguardConfigurationBackup')
def API_deleteWireguardConfigurationBackup():
    data = request.get_json()
    if ("ConfigurationName" not in data.keys() or 
            "BackupFileName" not in data.keys() or
            len(data['ConfigurationName']) == 0 or 
            len(data['BackupFileName']) == 0):
        return ResponseObject(False, 
        "Please provide configurationName and backupFileName in body",  status_code=400)
    configurationName = data['ConfigurationName']
    backupFileName = data['BackupFileName']
    if configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist", status_code=404)
    
    status = WireguardConfigurations[configurationName].deleteBackup(backupFileName)
    return ResponseObject(status=status, message=(None if status else 'Backup file does not exist'), 
                          status_code = (200 if status else 404))

@app.get(f'{APP_PREFIX}/api/downloadWireguardConfigurationBackup')
def API_downloadWireguardConfigurationBackup():
    configurationName = os.path.basename(request.args.get('configurationName'))
    backupFileName = os.path.basename(request.args.get('backupFileName'))

    if configurationName is None or configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist", status_code=404)

    status, zip = WireguardConfigurations[configurationName].downloadBackup(backupFileName)

    if not status:
        current_app.logger.error(f"Failed to download a requested backup.\nConfiguration Name: {configurationName}\nBackup File Name: {backupFileName}")
        return ResponseObject(False, "Internal server error", status_code=500)

    return send_file(os.path.join('download', zip), as_attachment=True)

@app.post(f'{APP_PREFIX}/api/restoreWireguardConfigurationBackup')
def API_restoreWireguardConfigurationBackup():
    data = request.get_json()
    if ("ConfigurationName" not in data.keys() or
            "BackupFileName" not in data.keys() or
            len(data['ConfigurationName']) == 0 or
            len(data['BackupFileName']) == 0):
        return ResponseObject(False,
                              "Please provide ConfigurationName and BackupFileName in body", status_code=400)
    configurationName = data['ConfigurationName']
    backupFileName = data['BackupFileName']
    if configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist", status_code=404)
    
    status = WireguardConfigurations[configurationName].restoreBackup(backupFileName)
    return ResponseObject(status=status, message=(None if status else 'Restore backup failed'))
    
@app.get(f'{APP_PREFIX}/api/getDashboardConfiguration')
def API_getDashboardConfiguration():
    return ResponseObject(data=DashboardConfig.toJson())


@app.get(f'{APP_PREFIX}/api/getAvailableTimezones')
def API_getAvailableTimezones():
    return ResponseObject(data=sorted(available_timezones()))


def _get_server_datetime_info_for_ui() -> tuple[str, str]:
    """
    Authoritative OS clock + IANA zone for Settings UI.
    Uses timedatectl + ZoneInfo so we match `timedatectl` in shell even when the
    Gunicorn process has TZ=UTC or tzlocal returns the wrong zone.
    """
    bin_path = shutil.which("timedatectl")
    if bin_path:
        try:
            p = subprocess.run(
                [bin_path, "show", "--property=Timezone", "--value"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if p.returncode == 0:
                tz_name = (p.stdout or "").strip()
                if tz_name:
                    try:
                        local_now = datetime.now(ZoneInfo(tz_name)).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        return local_now, tz_name
                    except Exception:
                        pass
        except Exception:
            pass
    tz_name = None
    try:
        from tzlocal import get_localzone_name
        tz_name = get_localzone_name()
    except Exception:
        pass
    if not tz_name and os.path.exists("/etc/localtime"):
        try:
            rp = os.path.realpath("/etc/localtime")
            if "zoneinfo" in rp:
                tz_name = rp.split("zoneinfo/")[-1]
        except Exception:
            pass
    if not tz_name:
        try:
            lt = time.localtime()
            tz_name = time.tzname[1 if lt.tm_isdst else 0]
        except Exception:
            tz_name = None

    now_local = datetime.now()
    return now_local.strftime("%Y-%m-%d %H:%M:%S"), (tz_name or "unknown")


@app.get(f'{APP_PREFIX}/api/getServerDateTimeInfo')
def API_getServerDateTimeInfo():
    """Current OS local time and system timezone (for Settings status line)."""
    local_now, tz_name = _get_server_datetime_info_for_ui()
    return ResponseObject(data={
        "local_now": local_now,
        "system_timezone": tz_name,
    })


def _resolve_nginx_binary() -> str | None:
    """PATH first, then common install locations (manual installs may omit PATH for Gunicorn)."""
    p = shutil.which("nginx")
    if p:
        return p
    for path in (
        "/usr/sbin/nginx",
        "/usr/local/sbin/nginx",
        "/usr/local/nginx/sbin/nginx",
        "/opt/nginx/sbin/nginx",
    ):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


@app.get(f'{APP_PREFIX}/api/getNginxRuntimeInfo')
def API_getNginxRuntimeInfo():
    """Detect nginx binary on the host running WGDashboard (admin session). Read-only."""
    bin_path = _resolve_nginx_binary()
    if not bin_path:
        return ResponseObject(data={
            "installed": False,
            "binary_path": None,
            "version_line": None,
            "error": None,
        })
    try:
        p = subprocess.run(
            [bin_path, "-v"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        err_out = (p.stderr or "").strip()
        std_out = (p.stdout or "").strip()
        version_line = (err_out or std_out).split("\n")[0] or None
        err_msg = None
        if p.returncode != 0:
            err_msg = version_line or f"nginx -v exited {p.returncode}"
        return ResponseObject(data={
            "installed": True,
            "binary_path": bin_path,
            "version_line": version_line,
            "error": err_msg,
        })
    except subprocess.TimeoutExpired:
        return ResponseObject(data={
            "installed": True,
            "binary_path": bin_path,
            "version_line": None,
            "error": "nginx -v timed out",
        })
    except Exception as e:
        return ResponseObject(data={
            "installed": True,
            "binary_path": bin_path,
            "version_line": None,
            "error": str(e),
        })


_NGINX_STOCK_DEFAULT_SITE_PATHS = (
    "/etc/nginx/sites-enabled/default",
    "/etc/nginx/sites-enabled/default.conf",
)


def _curl_http_code_via_unix_socket(socket_path: str) -> tuple[str | None, str]:
    """HTTP GET / via curl --unix-socket (checks Gunicorn on the socket)."""
    curl = shutil.which("curl")
    if not curl:
        return None, "curl not found on PATH"
    try:
        p = subprocess.run(
            [
                curl,
                "-sS",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "--connect-timeout",
                "3",
                "--unix-socket",
                socket_path,
                "http://127.0.0.1/",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = (p.stdout or "").strip()
        if p.returncode == 0 and out.isdigit():
            return out, ""
        err = ((p.stderr or "") + (p.stdout or "")).strip()
        return None, err or f"curl exit {p.returncode}"
    except subprocess.TimeoutExpired:
        return None, "curl timed out"
    except Exception as e:
        return None, str(e)


def _nginx_wgdashboard_proxy_pass_preview() -> str | None:
    for path in (
        "/etc/nginx/sites-available/wgdashboard.conf",
        "/etc/nginx/conf.d/wgdashboard.conf",
    ):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("proxy_pass") and "unix:" in s:
                        return s
        except OSError:
            continue
    return None


def _collect_nginx_stock_default_status() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in _NGINX_STOCK_DEFAULT_SITE_PATHS:
        row: dict[str, object] = {"path": path, "exists": os.path.lexists(path)}
        if os.path.islink(path):
            try:
                row["symlink_target"] = os.readlink(path)
            except OSError:
                row["symlink_target"] = None
        rows.append(row)
    return rows


@app.get(f'{APP_PREFIX}/api/getListenStackDiagnostics')
def API_getListenStackDiagnostics():
    """
    Read-only: socket path, curl-to-socket, Nginx stock default sites, wgdashboard proxy line.
    Admin session only.
    """
    if session.get("role") != "admin":
        return ResponseObject(False, "Admin session required.", status_code=403)
    _, mode = DashboardConfig.GetConfig("Server", "app_listen_mode")
    mode_s = (str(mode or "").strip()).lower()
    socket_abs = _abs_gunicorn_socket_path_for_nginx()
    sock_exists = bool(socket_abs and os.path.lexists(socket_abs))
    sock_is_sock = False
    if socket_abs and os.path.exists(socket_abs):
        try:
            sock_is_sock = stat.S_ISSOCK(os.stat(socket_abs, follow_symlinks=False).st_mode)
        except OSError:
            sock_is_sock = False

    http_code, curl_err = (None, "")
    if mode_s == "nginx_socket" and socket_abs and sock_exists:
        http_code, curl_err = _curl_http_code_via_unix_socket(socket_abs)
    elif mode_s != "nginx_socket":
        curl_err = "Skipped (app_listen_mode is not nginx_socket)."
    elif not socket_abs:
        curl_err = "No resolved socket path."
    else:
        curl_err = "Socket path does not exist (is Gunicorn running?)."

    return ResponseObject(
        data={
            "app_listen_mode": mode_s,
            "gunicorn_socket_resolved_abs": socket_abs or "",
            "socket_node_exists": sock_exists,
            "socket_is_listening_socket": sock_is_sock,
            "curl_unix_socket_http_code": http_code,
            "curl_unix_socket_error": curl_err,
            "nginx_wgdashboard_proxy_pass_line": _nginx_wgdashboard_proxy_pass_preview(),
            "nginx_stock_default_sites": _collect_nginx_stock_default_status(),
            "hint": (
                "If curl shows 200/302/401 but the browser shows Welcome to nginx, the stock "
                "default site is still enabled — deploy with “disable stock default” or remove "
                "/etc/nginx/sites-enabled/default."
            ),
        }
    )


def _validate_nginx_server_name_for_deploy(name: str) -> tuple[bool, str]:
    s = (name or "").strip()
    if len(s) < 1 or len(s) > 253:
        return False, "server_name must be 1–253 characters."
    if not re.match(r"^[a-zA-Z0-9._-]+$", s):
        return False, "server_name contains invalid characters."
    return True, ""


def _abs_gunicorn_socket_path_for_nginx() -> str:
    exist, raw = DashboardConfig.GetConfig("Server", "gunicorn_socket_path")
    p = (str(raw) if exist and raw is not None else "").strip()
    if not p:
        return ""
    if p.startswith("/"):
        return os.path.normpath(p)
    base = DashboardConfig.ConfigurationPath
    if not os.path.isabs(base):
        base = os.path.abspath(base)
    return os.path.normpath(os.path.join(base, p))


def _build_wgdashboard_nginx_site_config(
    server_name: str,
    socket_abs: str,
    app_prefix: str,
    *,
    default_server: bool = False,
) -> str:
    prefix_note = ""
    if (app_prefix or "").strip():
        prefix_note = (
            f'# app_prefix in wg-dashboard.ini is "{app_prefix.strip()}" — '
            "adjust location if your dashboard is under a subpath.\n"
        )
    if default_server:
        prefix_note += (
            "# listen default_server: use when opening the dashboard by IP, or remove "
            "/etc/nginx/sites-enabled/default if nginx -t reports duplicate default_server.\n"
        )
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if default_server:
        listen_block = "    listen 80 default_server;\n"
        name_block = "    server_name _;\n"
    else:
        listen_block = "    listen 80;\n"
        name_block = f"    server_name {server_name};\n"
    return (
        f"{prefix_note}"
        f"# Generated by WGDashboard — {ts}\n"
        "server {\n"
        f"{listen_block}"
        f"{name_block}\n"
        "    location / {\n"
        "        proxy_set_header Host $host;\n"
        "        proxy_set_header X-Real-IP $remote_addr;\n"
        "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
        "        proxy_set_header X-Forwarded-Proto $scheme;\n"
        f"        proxy_pass http://unix:{socket_abs}:;\n"
        "    }\n"
        "}\n"
    )


def _nginx_deploy_target_path() -> tuple[str | None, str | None]:
    """Returns (file_path, layout) where layout is sites_available or conf_d."""
    sa_dir = "/etc/nginx/sites-available"
    se_dir = "/etc/nginx/sites-enabled"
    conf_d_dir = "/etc/nginx/conf.d"
    if os.path.isdir(sa_dir) and os.path.isdir(se_dir):
        return os.path.join(sa_dir, "wgdashboard.conf"), "sites_available"
    if os.path.isdir(conf_d_dir):
        return os.path.join(conf_d_dir, "wgdashboard.conf"), "conf_d"
    return None, None


def _run_nginx_test(nginx_bin: str) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            [nginx_bin, "-t"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = ((p.stderr or "") + "\n" + (p.stdout or "")).strip()
        if p.returncode == 0:
            return True, combined or "ok"
        return False, combined or f"nginx -t exited {p.returncode}"
    except subprocess.TimeoutExpired:
        return False, "nginx -t timed out"
    except Exception as e:
        return False, str(e)


def _reload_nginx(nginx_bin: str) -> tuple[bool, str]:
    candidates = [
        ["systemctl", "reload", "nginx"],
        ["/bin/systemctl", "reload", "nginx"],
        ["/usr/bin/systemctl", "reload", "nginx"],
        ["service", "nginx", "reload"],
        [nginx_bin, "-s", "reload"],
    ]
    last_err = ""
    for cmd in candidates:
        exe = cmd[0]
        if os.path.isabs(exe):
            if not (os.path.isfile(exe) and os.access(exe, os.X_OK)):
                continue
        else:
            w = shutil.which(exe)
            if w is None:
                continue
            cmd = [w] + cmd[1:]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if p.returncode == 0:
                return True, ""
            last_err = (p.stderr or p.stdout or "").strip() or f"exit {p.returncode}"
        except Exception as e:
            last_err = str(e)
    return False, last_err or "Could not reload nginx."


def _remove_nginx_stock_default_symlinks() -> list[tuple[str, str]]:
    """Remove Debian/Ubuntu stock default site symlinks; return list for rollback."""
    removed: list[tuple[str, str]] = []
    for path in _NGINX_STOCK_DEFAULT_SITE_PATHS:
        if not os.path.islink(path):
            continue
        try:
            tgt = os.readlink(path)
            os.remove(path)
            removed.append((path, tgt))
        except OSError:
            continue
    return removed


def _rollback_wgdashboard_nginx_deploy(
    target_path: str,
    backup: str | None,
    se_path: str,
    created_symlink: bool,
    layout: str,
    removed_stock_defaults: list[tuple[str, str]] | None = None,
) -> None:
    if removed_stock_defaults:
        for spath, tgt in removed_stock_defaults:
            try:
                if not os.path.lexists(spath):
                    os.symlink(tgt, spath)
            except OSError:
                pass
    if layout == "sites_available" and created_symlink:
        try:
            os.remove(se_path)
        except OSError:
            pass
    if backup is not None:
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(backup)
        except OSError:
            pass
    else:
        try:
            if os.path.isfile(target_path):
                os.remove(target_path)
        except OSError:
            pass


@app.post(f'{APP_PREFIX}/api/deployWgDashboardNginx')
def API_deployWgDashboardNginx():
    """Write example site config under /etc/nginx (admin only). Requires root or matching sudoers."""
    if session.get("role") != "admin":
        return ResponseObject(False, "Admin session required.", status_code=403)
    data = request.get_json(silent=True) or {}
    use_default_server = bool(data.get("default_server"))
    disable_stock_default_site = bool(data.get("disable_stock_default_site"))
    server_name = (data.get("server_name") or "").strip()
    if not use_default_server:
        ok, msg = _validate_nginx_server_name_for_deploy(server_name)
        if not ok:
            return ResponseObject(False, msg)
    _, mode = DashboardConfig.GetConfig("Server", "app_listen_mode")
    mode = (str(mode or "").strip()).lower()
    if mode != "nginx_socket":
        return ResponseObject(
            False,
            "Set listen mode to Behind Nginx (Unix socket) before deploying.",
        )
    socket_abs = _abs_gunicorn_socket_path_for_nginx()
    if not socket_abs or not socket_abs.startswith("/"):
        return ResponseObject(False, "Set a valid absolute gunicorn_socket_path in Settings.")
    nginx_bin = _resolve_nginx_binary()
    if not nginx_bin:
        return ResponseObject(False, "nginx binary not found.")
    target_path, layout = _nginx_deploy_target_path()
    if not target_path or not layout:
        return ResponseObject(
            False,
            "Could not find /etc/nginx/sites-available or /etc/nginx/conf.d.",
        )
    _, ap = DashboardConfig.GetConfig("Server", "app_prefix")
    app_prefix = str(ap or "")
    content = _build_wgdashboard_nginx_site_config(
        server_name,
        socket_abs,
        app_prefix,
        default_server=use_default_server,
    )

    se_path = "/etc/nginx/sites-enabled/wgdashboard.conf"
    backup = None
    if os.path.isfile(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                backup = f.read()
        except OSError as e:
            return ResponseObject(False, f"Could not read existing file: {e}")

    created_symlink = False
    removed_stock_defaults: list[tuple[str, str]] = []
    try:
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)
        except PermissionError:
            return ResponseObject(
                False,
                "Permission denied writing to /etc/nginx. Run WGDashboard as root (e.g. sudo ./wgd.sh start) or configure sudoers — see implementasi-nginx-gunicorn-socket.md.",
            )
        except OSError as e:
            return ResponseObject(False, str(e))

        if layout == "sites_available":
            if os.path.lexists(se_path):
                if os.path.islink(se_path):
                    if os.path.realpath(se_path) != os.path.realpath(target_path):
                        _rollback_wgdashboard_nginx_deploy(
                            target_path, backup, se_path, created_symlink, layout, None
                        )
                        return ResponseObject(
                            False,
                            "sites-enabled/wgdashboard.conf exists and points elsewhere; fix manually.",
                        )
                else:
                    _rollback_wgdashboard_nginx_deploy(
                        target_path, backup, se_path, created_symlink, layout, None
                    )
                    return ResponseObject(
                        False,
                        "sites-enabled/wgdashboard.conf exists and is not a symlink; fix manually.",
                    )
            else:
                os.symlink(target_path, se_path)
                created_symlink = True

        if disable_stock_default_site:
            removed_stock_defaults = _remove_nginx_stock_default_symlinks()

        ok_test, err_msg = _run_nginx_test(nginx_bin)
        if not ok_test:
            _rollback_wgdashboard_nginx_deploy(
                target_path, backup, se_path, created_symlink, layout, removed_stock_defaults
            )
            return ResponseObject(False, f"nginx -t failed:\n{err_msg}")

        r_ok, r_err = _reload_nginx(nginx_bin)
        if not r_ok:
            return ResponseObject(
                True,
                message=(
                    f"Config written to {target_path}. Reload failed: {r_err}. "
                    "Run manually: sudo systemctl reload nginx"
                ),
                data={
                    "written_path": target_path,
                    "layout": layout,
                    "nginx_t": "ok",
                    "reload": "failed",
                    "removed_stock_default_sites": [p for p, _ in removed_stock_defaults],
                },
            )
        return ResponseObject(
            True,
            data={
                "written_path": target_path,
                "layout": layout,
                "nginx_t": "ok",
                "reload": "ok",
                "removed_stock_default_sites": [p for p, _ in removed_stock_defaults],
            },
        )
    except OSError as e:
        _rollback_wgdashboard_nginx_deploy(
            target_path, backup, se_path, created_symlink, layout, removed_stock_defaults
        )
        return ResponseObject(False, str(e))


def _resolve_wgdashboard_systemd_unit() -> str:
    env_u = (os.environ.get("WGDASHBOARD_SYSTEMD_UNIT") or "").strip()
    if env_u:
        return env_u
    _, raw = DashboardConfig.GetConfig("Server", "systemd_unit")
    return (str(raw or "").strip())


def _schedule_wgdashboard_restart(delay_seconds: float = 2.0) -> tuple[bool, str]:
    """Fork a delayed restart so the HTTP response can finish before the process stops."""
    unit = _resolve_wgdashboard_systemd_unit()
    try:
        delay = float(delay_seconds)
    except (TypeError, ValueError):
        return False, "Invalid delay_seconds."
    delay = max(0.5, min(10.0, delay))

    if unit:
        ok, msg = DashboardConfig.validate_systemd_unit(unit)
        if not ok:
            return False, msg
        cmd = f"sleep {delay}; systemctl restart {shlex.quote(unit)}"
    else:
        dashboard_dir = os.path.dirname(os.path.abspath(__file__))
        wgd_sh = os.path.join(dashboard_dir, "wgd.sh")
        if not os.path.isfile(wgd_sh):
            return (
                False,
                "wgd.sh not found beside dashboard.py. Set systemd_unit in Settings or "
                "environment variable WGDASHBOARD_SYSTEMD_UNIT.",
            )
        if not os.access(wgd_sh, os.X_OK):
            return False, "wgd.sh is not executable."
        cmd = (
            f"sleep {delay}; cd {shlex.quote(dashboard_dir)} && exec ./wgd.sh restart"
        )

    try:
        subprocess.Popen(
            ["/bin/bash", "-c", cmd],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        return False, str(e)
    return True, ""


@app.post(f'{APP_PREFIX}/api/restartWgDashboardService')
def API_restartWgDashboardService():
    """Schedule WGDashboard process restart (admin only). Finishes HTTP before restart."""
    if session.get("role") != "admin":
        return ResponseObject(False, "Admin session required.", status_code=403)
    data = request.get_json(silent=True) or {}
    try:
        delay = float(data.get("delay_seconds", 2.0))
    except (TypeError, ValueError):
        return ResponseObject(False, "Invalid delay_seconds.")
    ok, err = _schedule_wgdashboard_restart(delay)
    if not ok:
        return ResponseObject(False, err)
    unit = _resolve_wgdashboard_systemd_unit()
    via = f"systemd ({unit})" if unit else "wgd.sh restart"
    message = (
        f"Restart scheduled ({via}). This page may disconnect; refresh after a few seconds."
    )
    return ResponseObject(True, message=message, data={"scheduled": True, "via": via})


def apply_system_timezone_linux(tz: str) -> tuple[bool, str]:
    """Apply OS timezone via systemd timedatectl. Direct if root; else sudo -n if NOPASSWD is configured."""
    bin_path = shutil.which("timedatectl")
    if not bin_path:
        return False, "timedatectl not found; systemd-based Linux is required."
    try:
        p = subprocess.run(
            [bin_path, "set-timezone", tz],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if p.returncode == 0:
            return True, ""
        err_direct = (p.stderr or p.stdout or "").strip() or f"exit code {p.returncode}"
        sudo_path = shutil.which("sudo")
        if not sudo_path:
            return False, err_direct
        p2 = subprocess.run(
            [sudo_path, "-n", bin_path, "set-timezone", tz],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if p2.returncode == 0:
            return True, ""
        err_sudo = (p2.stderr or p2.stdout or "").strip() or str(p2.returncode)
        return False, f"{err_direct} | sudo -n: {err_sudo}"
    except subprocess.TimeoutExpired:
        return False, "timedatectl timed out"
    except Exception as e:
        return False, str(e)


@app.post(f'{APP_PREFIX}/api/updateDashboardConfigurationItem')
def API_updateDashboardConfigurationItem():
    data = request.get_json()
    if "section" not in data.keys() or "key" not in data.keys() or "value" not in data.keys():
        return ResponseObject(False, "Invalid request.")
    if data["section"] == "Server" and data["key"] == "clients_statistics_interval":
        try:
            ms = int(str(data["value"]).strip())
        except (TypeError, ValueError):
            return ResponseObject(False, "Invalid clients statistics interval.")
        data["value"] = str(ClientsNetworkOverviewStats.clamp_interval_ms(ms))
    if data["section"] == "Server" and data["key"] == "dashboard_timezone":
        data["value"] = str(data["value"]).strip()
        ok_tz, msg_tz = DashboardConfig.validate_server_timezone(data["value"])
        if not ok_tz:
            return ResponseObject(False, msg_tz)
        ok_os, msg_os = apply_system_timezone_linux(data["value"])
        if not ok_os:
            return ResponseObject(False, f"Could not set OS timezone (timedatectl): {msg_os}")
    if data["section"] == "Server" and data["key"] == "login_copyright_url":
        data["value"] = str(data["value"]).strip()
    if data["section"] == "Server" and data["key"] == "app_listen_mode":
        data["value"] = str(data["value"]).strip()
    if data["section"] == "Server" and data["key"] == "gunicorn_socket_path":
        data["value"] = str(data["value"]).strip()
    if data["section"] == "Server" and data["key"] == "systemd_unit":
        data["value"] = str(data["value"]).strip()
    valid, msg = DashboardConfig.SetConfig(
        data["section"], data["key"], data['value'])
    if not valid:
        return ResponseObject(False, msg)
    if data['section'] == "Server":
        if data['key'] == 'clients_statistics_interval':
            reschedule_clients_network_overview_job()
        if data['key'] == 'wg_conf_path':
            WireguardConfigurations.clear()
            WireguardConfigurations.clear()
            InitWireguardConfigurationsList()
    return ResponseObject(True, data=DashboardConfig.GetConfig(data["section"], data["key"])[1])

@app.get(f'{APP_PREFIX}/api/getDashboardAPIKeys')
def API_getDashboardAPIKeys():
    if DashboardConfig.GetConfig('Server', 'dashboard_api_key'):
        return ResponseObject(data=DashboardConfig.DashboardAPIKeys)
    return ResponseObject(False, "WGDashboard API Keys function is disabled")

@app.post(f'{APP_PREFIX}/api/newDashboardAPIKey')
def API_newDashboardAPIKey():
    data = request.get_json()
    if DashboardConfig.GetConfig('Server', 'dashboard_api_key'):
        try:
            if data['NeverExpire']:
                expiredAt = None
            else:
                expiredAt = datetime.strptime(data['ExpiredAt'], '%Y-%m-%d %H:%M:%S')
            DashboardConfig.createAPIKeys(expiredAt)
            return ResponseObject(True, data=DashboardConfig.DashboardAPIKeys)
        except Exception as e:
            return ResponseObject(False, str(e))
    return ResponseObject(False, "Dashboard API Keys function is disbaled")

@app.post(f'{APP_PREFIX}/api/deleteDashboardAPIKey')
def API_deleteDashboardAPIKey():
    data = request.get_json()
    if DashboardConfig.GetConfig('Server', 'dashboard_api_key'):
        if len(data['Key']) > 0 and len(list(filter(lambda x : x.Key == data['Key'], DashboardConfig.DashboardAPIKeys))) > 0:
            DashboardConfig.deleteAPIKey(data['Key'])
            return ResponseObject(True, data=DashboardConfig.DashboardAPIKeys)
        else:
            return ResponseObject(False, "API Key does not exist", status_code=404)
    return ResponseObject(False, "Dashboard API Keys function is disbaled")
    
@app.post(f'{APP_PREFIX}/api/updatePeerSettings/<configName>')
def API_updatePeerSettings(configName):
    data = request.get_json()
    id = data['id']
    if len(id) > 0 and configName in WireguardConfigurations.keys():
        name = data['name']
        private_key = data['private_key']
        dns_addresses = data['DNS']
        allowed_ip = data['allowed_ip']
        endpoint_allowed_ip = data['endpoint_allowed_ip']
        preshared_key = data['preshared_key']
        mtu = data['mtu']
        keepalive = data['keepalive']
        wireguardConfig = WireguardConfigurations[configName]
        foundPeer, peer = wireguardConfig.searchPeer(id)
        if foundPeer:
            if wireguardConfig.Protocol == 'wg':
                status, msg = peer.updatePeer(name, private_key, preshared_key, dns_addresses,
                                       allowed_ip, endpoint_allowed_ip, mtu, keepalive)
            else:
                status, msg = peer.updatePeer(name, private_key, preshared_key, dns_addresses,
                    allowed_ip, endpoint_allowed_ip, mtu, keepalive, "off")
            wireguardConfig.getPeers()
            DashboardWebHooks.RunWebHook('peer_updated', {
                "configuration": wireguardConfig.Name,
                "peers": [id]
            })
            return ResponseObject(status, msg)
            
    return ResponseObject(False, "Peer does not exist")

@app.post(f'{APP_PREFIX}/api/resetPeerData/<configName>')
def API_resetPeerData(configName):
    data = request.get_json()
    id = data['id']
    type = data['type']
    if len(id) == 0 or configName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration/Peer does not exist")
    wgc = WireguardConfigurations.get(configName)
    foundPeer, peer = wgc.searchPeer(id)
    if not foundPeer:
        return ResponseObject(False, "Configuration/Peer does not exist")
    
    resetStatus = peer.resetDataUsage(type)
    if resetStatus:
        wgc.restrictPeers([id])
        wgc.allowAccessPeers([id])
    
    return ResponseObject(status=resetStatus)

@app.post(f'{APP_PREFIX}/api/deletePeers/<configName>')
def API_deletePeers(configName: str) -> ResponseObject:
    data = request.get_json()
    peers = data['peers']
    if configName in WireguardConfigurations.keys():
        if len(peers) == 0:
            return ResponseObject(False, "Please specify one or more peers", status_code=400)
        configuration = WireguardConfigurations.get(configName)
        status, msg = configuration.deletePeers(peers, AllPeerJobs, AllPeerShareLinks)
        
        # Delete Assignment
        
        for p in peers:
            assignments = DashboardClients.DashboardClientsPeerAssignment.GetAssignedClients(configName, p)
            for c in assignments:
                DashboardClients.DashboardClientsPeerAssignment.UnassignClients(c.AssignmentID)
        
        return ResponseObject(status, msg)

    return ResponseObject(False, "Configuration does not exist", status_code=404)

@app.post(f'{APP_PREFIX}/api/restrictPeers/<configName>')
def API_restrictPeers(configName: str) -> ResponseObject:
    data = request.get_json()
    peers = data['peers']
    if configName in WireguardConfigurations.keys():
        if len(peers) == 0:
            return ResponseObject(False, "Please specify one or more peers")
        configuration = WireguardConfigurations.get(configName)
        status, msg = configuration.restrictPeers(peers)
        return ResponseObject(status, msg)
    return ResponseObject(False, "Configuration does not exist", status_code=404)

@app.post(f'{APP_PREFIX}/api/sharePeer/create')
def API_sharePeer_create():
    data: dict[str, str] = request.get_json()
    Configuration = data.get('Configuration')
    Peer = data.get('Peer')
    ExpireDate = data.get('ExpireDate')
    if Configuration is None or Peer is None:
        return ResponseObject(False, "Please specify configuration and peers")
    activeLink = AllPeerShareLinks.getLink(Configuration, Peer)
    if len(activeLink) > 0:
        return ResponseObject(True, 
                              "This peer is already sharing. Please view data for shared link.",
                                data=activeLink[0]
        )
    status, message = AllPeerShareLinks.addLink(Configuration, Peer, datetime.strptime(ExpireDate, "%Y-%m-%d %H:%M:%S"))
    if not status:
        return ResponseObject(status, message)
    return ResponseObject(data=AllPeerShareLinks.getLinkByID(message))

@app.post(f'{APP_PREFIX}/api/sharePeer/update')
def API_sharePeer_update():
    data: dict[str, str] = request.get_json()
    ShareID: str = data.get("ShareID")
    ExpireDate: str = data.get("ExpireDate")
    
    if not all([ShareID, ExpireDate]):
        return ResponseObject(False, "Please specify ShareID")
    
    if len(AllPeerShareLinks.getLinkByID(ShareID)) == 0:
        return ResponseObject(False, "ShareID does not exist")
    
    status, message = AllPeerShareLinks.updateLinkExpireDate(ShareID, datetime.strptime(ExpireDate, "%Y-%m-%d %H:%M:%S"))
    if not status:
        return ResponseObject(status, message)
    return ResponseObject(data=AllPeerShareLinks.getLinkByID(ShareID))

@app.get(f'{APP_PREFIX}/api/sharePeer/get')
def API_sharePeer_get():
    data = request.args
    ShareID = data.get("ShareID")
    if ShareID is None or len(ShareID) == 0:
        return ResponseObject(False, "Please provide ShareID")
    link = AllPeerShareLinks.getLinkByID(ShareID)
    if len(link) == 0:
        return ResponseObject(False, "This link is either expired to invalid")
    l = link[0]
    if l.Configuration not in WireguardConfigurations.keys():
        return ResponseObject(False, "The peer you're looking for does not exist")
    c = WireguardConfigurations.get(l.Configuration)
    fp, p = c.searchPeer(l.Peer)
    if not fp:
        return ResponseObject(False, "The peer you're looking for does not exist")
    
    return ResponseObject(data=p.downloadPeer())
    
@app.post(f'{APP_PREFIX}/api/allowAccessPeers/<configName>')
def API_allowAccessPeers(configName: str) -> ResponseObject:
    data = request.get_json()
    peers = data['peers']
    if configName in WireguardConfigurations.keys():
        if len(peers) == 0:
            return ResponseObject(False, "Please specify one or more peers")
        configuration = WireguardConfigurations.get(configName)
        status, msg = configuration.allowAccessPeers(peers)
        return ResponseObject(status, msg)
    return ResponseObject(False, "Configuration does not exist")

@app.post(f'{APP_PREFIX}/api/addPeers/<configName>')
def API_addPeers(configName):
    if configName in WireguardConfigurations.keys():
        data: dict = request.get_json()
        try:
            

            bulkAdd: bool = data.get("bulkAdd", False)
            bulkAddAmount: int = data.get('bulkAddAmount', 0)
            preshared_key_bulkAdd: bool = data.get('preshared_key_bulkAdd', False)

            public_key: str = data.get('public_key', "")
            allowed_ips: list[str] = data.get('allowed_ips', [])
            allowed_ips_validation: bool = data.get('allowed_ips_validation', True)
            
            endpoint_allowed_ip: str = data.get('endpoint_allowed_ip', DashboardConfig.GetConfig("Peers", "peer_endpoint_allowed_ip")[1])
            dns_addresses: str = data.get('DNS', DashboardConfig.GetConfig("Peers", "peer_global_DNS")[1])
            
            
            mtu: int = data.get('mtu', None)
            keep_alive: int = data.get('keepalive', None)
            preshared_key: str = data.get('preshared_key', "")            
    
            if type(mtu) is not int or mtu < 0 or mtu > 1460:
                default: str = DashboardConfig.GetConfig("Peers", "peer_mtu")[1]
                if default.isnumeric():
                    try:
                        mtu = int(default)
                    except Exception as e:
                        mtu = 0
                else:
                    mtu = 0
            if type(keep_alive) is not int or keep_alive < 0:
                default = DashboardConfig.GetConfig("Peers", "peer_keep_alive")[1]
                if default.isnumeric():
                    try:
                        keep_alive = int(default)
                    except Exception as e:
                        keep_alive = 0
                else:
                    keep_alive = 0
            
            config = WireguardConfigurations.get(configName)
            if not config.getStatus():
                config.toggleConfiguration()
            ipStatus, availableIps = config.getAvailableIP(-1)
            ipCountStatus, numberOfAvailableIPs = config.getNumberOfAvailableIP()
            defaultIPSubnet = list(availableIps.keys())[0]
            if bulkAdd:
                if type(preshared_key_bulkAdd) is not bool:
                    preshared_key_bulkAdd = False
                if type(bulkAddAmount) is not int or bulkAddAmount < 1:
                    return ResponseObject(False, "Please specify amount of peers you want to add")
                if not ipStatus:
                    return ResponseObject(False, "No more available IP can assign")
                if len(availableIps.keys()) == 0:
                    return ResponseObject(False, "This configuration does not have any IP address available")
                if bulkAddAmount > sum(list(numberOfAvailableIPs.values())):
                    return ResponseObject(False,
                            f"The maximum number of peers can add is {sum(list(numberOfAvailableIPs.values()))}")
                keyPairs = []
                addedCount = 0
                for subnet in availableIps.keys():
                    for ip in availableIps[subnet]:
                        newPrivateKey = GenerateWireguardPrivateKey()[1]
                        addedCount += 1
                        keyPairs.append({
                            "private_key": newPrivateKey,
                            "id": GenerateWireguardPublicKey(newPrivateKey)[1],
                            "preshared_key": (GenerateWireguardPrivateKey()[1] if preshared_key_bulkAdd else ""),
                            "allowed_ip": ip,
                            "name": f"BulkPeer_{(addedCount + 1)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                            "DNS": dns_addresses,
                            "endpoint_allowed_ip": endpoint_allowed_ip,
                            "mtu": mtu,
                            "keepalive": keep_alive,
                            "advanced_security": "off"
                        })
                        if addedCount == bulkAddAmount:
                            break
                    if addedCount == bulkAddAmount:
                        break
                if len(keyPairs) == 0 or (bulkAdd and len(keyPairs) != bulkAddAmount):
                    return ResponseObject(False, "Generating key pairs by bulk failed")
                status, addedPeers, message = config.addPeers(keyPairs)
                return ResponseObject(status=status, message=message, data=addedPeers)
    
            else:
                if config.searchPeer(public_key)[0] is True:
                    return ResponseObject(False, f"This peer already exist")
                name = data.get("name", "")
                private_key = data.get("private_key", "")

                if len(public_key) == 0:
                    if len(private_key) == 0:
                        private_key = GenerateWireguardPrivateKey()[1]
                        public_key = GenerateWireguardPublicKey(private_key)[1]
                    else:
                        public_key = GenerateWireguardPublicKey(private_key)[1]
                else:
                    if len(private_key) > 0:
                        genPub = GenerateWireguardPublicKey(private_key)[1]
                        # Check if provided pubkey match provided private key
                        if public_key != genPub:
                            return ResponseObject(False, "Provided Public Key does not match provided Private Key")
                if len(allowed_ips) == 0:
                    if ipStatus:
                        for subnet in availableIps.keys():
                            for ip in availableIps[subnet]:
                                allowed_ips = [ip]
                                break
                            break  
                    else:
                        return ResponseObject(False, "No more available IP can assign") 

                if allowed_ips_validation:
                    for i in allowed_ips:
                        found = False
                        for subnet in availableIps.keys():
                            network = ipaddress.ip_network(subnet, False)
                            ap = ipaddress.ip_network(i)
                            if network.version == ap.version and ap.subnet_of(network):
                                found = True
                        
                        if not found:
                            return ResponseObject(False, f"This IP is not available: {i}")

                status, addedPeers, message = config.addPeers([
                    {
                        "name": name,
                        "id": public_key,
                        "private_key": private_key,
                        "allowed_ip": ','.join(allowed_ips),
                        "preshared_key": preshared_key,
                        "endpoint_allowed_ip": endpoint_allowed_ip,
                        "DNS": dns_addresses,
                        "mtu": mtu,
                        "keepalive": keep_alive,
                        "advanced_security": "off"
                    }]
                )
                return ResponseObject(status=status, message=message, data=addedPeers)
        except Exception as e:
            app.logger.error("Add peers failed", e)
            return ResponseObject(False,
                                  f"Add peers failed. Reason: {message}")

    return ResponseObject(False, "Configuration does not exist")

@app.get(f"{APP_PREFIX}/api/downloadPeer/<configName>")
def API_downloadPeer(configName):
    data = request.args
    if configName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist")
    configuration = WireguardConfigurations[configName]
    peerFound, peer = configuration.searchPeer(data['id'])
    if len(data['id']) == 0 or not peerFound:
        return ResponseObject(False, "Peer does not exist")
    return ResponseObject(data=peer.downloadPeer())

@app.get(f"{APP_PREFIX}/api/downloadAllPeers/<configName>")
def API_downloadAllPeers(configName):
    if configName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist")
    configuration = WireguardConfigurations[configName]
    peerData = []
    untitledPeer = 0
    for i in configuration.Peers:
        file = i.downloadPeer()
        if file["fileName"] == "UntitledPeer":
            file["fileName"] = str(untitledPeer) + "_" + file["fileName"]
            untitledPeer += 1
        peerData.append(file)
    return ResponseObject(data=peerData)

@app.get(f"{APP_PREFIX}/api/getAvailableIPs/<configName>")
def API_getAvailableIPs(configName):
    if configName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist")
    status, ips = WireguardConfigurations.get(configName).getAvailableIP()
    return ResponseObject(status=status, data=ips)

@app.get(f"{APP_PREFIX}/api/getNumberOfAvailableIPs/<configName>")
def API_getNumberOfAvailableIPs(configName):
    if configName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist")
    status, ips = WireguardConfigurations.get(configName).getNumberOfAvailableIP()
    return ResponseObject(status=status, data=ips)

@app.get(f'{APP_PREFIX}/api/getWireguardConfigurationInfo')
def API_getConfigurationInfo():
    configurationName = request.args.get("configurationName")
    if not configurationName or configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Please provide configuration name")
    return ResponseObject(data={
        "configurationInfo": WireguardConfigurations[configurationName],
        "configurationPeers": WireguardConfigurations[configurationName].getPeersList(),
        "configurationRestrictedPeers": WireguardConfigurations[configurationName].getRestrictedPeersList()
    })

@app.get(f'{APP_PREFIX}/api/getPeerHistoricalEndpoints')
def API_GetPeerHistoricalEndpoints():
    configurationName = request.args.get("configurationName")
    id = request.args.get('id')
    if not configurationName or not id:
        return ResponseObject(False, "Please provide configurationName and id")
    fp, p = WireguardConfigurations.get(configurationName).searchPeer(id)
    if fp:
        result = p.getEndpoints()
        geo = {}
        try:
            r = requests.post(f"http://ip-api.com/batch?fields=city,country,lat,lon,query",
                              data=json.dumps([x['endpoint'] for x in result]))
            d = r.json()
            
                
        except Exception as e:
            return ResponseObject(data=result, message="Failed to request IP address geolocation. " + str(e))
        
        return ResponseObject(data={
            "endpoints": p.getEndpoints(),
            "geolocation": d
        })
    return ResponseObject(False, "Peer does not exist")

@app.get(f'{APP_PREFIX}/api/getPeerSessions')
def API_GetPeerSessions():
    configurationName = request.args.get("configurationName")
    id = request.args.get('id')
    try:
        startDate = request.args.get('startDate', None)
        endDate = request.args.get('endDate', None)
        
        if startDate is None:
            endDate = None
        else:
            startDate = datetime.strptime(startDate, "%Y-%m-%d")
            if endDate:
                endDate = datetime.strptime(endDate, "%Y-%m-%d")
                if startDate > endDate:
                    return ResponseObject(False, "startDate must be smaller than endDate")
    except Exception as e:
        return ResponseObject(False, "Dates are invalid")
    if not configurationName or not id:
        return ResponseObject(False, "Please provide configurationName and id")
    fp, p = WireguardConfigurations.get(configurationName).searchPeer(id)
    if fp:
        return ResponseObject(data=p.getSessions(startDate, endDate))
    return ResponseObject(False, "Peer does not exist")

@app.get(f'{APP_PREFIX}/api/getPeerTraffics')
def API_GetPeerTraffics():
    configurationName = request.args.get("configurationName")
    id = request.args.get('id')
    try:
        interval = request.args.get('interval', 30)
        startDate = request.args.get('startDate', None)
        endDate = request.args.get('endDate', None)
        if type(interval) is str:
            if not interval.isdigit():
                return ResponseObject(False, "Interval must be integers in minutes")
            interval = int(interval)
        if startDate is None:
            endDate = None
        else:
            startDate = datetime.strptime(startDate, "%Y-%m-%d")
            if endDate:
                endDate = datetime.strptime(endDate, "%Y-%m-%d")
                if startDate > endDate:
                    return ResponseObject(False, "startDate must be smaller than endDate")
    except Exception as e:
        return ResponseObject(False, "Dates are invalid" + e)
    if not configurationName or not id:
        return ResponseObject(False, "Please provide configurationName and id")
    fp, p = WireguardConfigurations.get(configurationName).searchPeer(id)
    if fp:
        return ResponseObject(data=p.getTraffics(interval, startDate, endDate))
    return ResponseObject(False, "Peer does not exist")

@app.get(f'{APP_PREFIX}/api/getPeerTrackingTableCounts')
def API_GetPeerTrackingTableCounts():
    configurationName = request.args.get("configurationName")
    if configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist")
    c = WireguardConfigurations.get(configurationName)
    return ResponseObject(data={
        "TrafficTrackingTableSize": c.getTransferTableSize(),
        "HistoricalTrackingTableSize": c.getHistoricalEndpointTableSize()
    })

@app.get(f'{APP_PREFIX}/api/downloadPeerTrackingTable')
def API_DownloadPeerTackingTable():
    configurationName = request.args.get("configurationName")
    table = request.args.get('table')
    if configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist")
    if table not in ['TrafficTrackingTable', 'HistoricalTrackingTable']:
        return ResponseObject(False, "Table does not exist")
    c = WireguardConfigurations.get(configurationName)
    return ResponseObject(
        data=c.downloadTransferTable() if table == 'TrafficTrackingTable' 
        else c.downloadHistoricalEndpointTable())

@app.post(f'{APP_PREFIX}/api/deletePeerTrackingTable')
def API_DeletePeerTrackingTable():
    data = request.get_json()
    configurationName = data.get('configurationName')
    table = data.get('table')
    if not configurationName or configurationName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist")
    if not table or table not in ['TrafficTrackingTable', 'HistoricalTrackingTable']:
        return ResponseObject(False, "Table does not exist")
    c = WireguardConfigurations.get(configurationName)
    return ResponseObject(
        status=c.deleteTransferTable() if table == 'TrafficTrackingTable'
        else c.deleteHistoryEndpointTable())

@app.get(f'{APP_PREFIX}/api/getDashboardTheme')
def API_getDashboardTheme():
    return ResponseObject(data=DashboardConfig.GetConfig("Server", "dashboard_theme")[1])

@app.get(f'{APP_PREFIX}/api/getDashboardVersion')
def API_getDashboardVersion():
    return ResponseObject(data=DashboardConfig.GetConfig("Server", "version")[1])


@app.get(f'{APP_PREFIX}/api/getLoginFooterSettings')
def API_getLoginFooterSettings():
    """Public: sign-in page footer (copyright line + optional link). {version} in text is expanded."""
    def _defaults():
        return (
            "Tunnela {version} | Developed with \u2764\ufe0f by Donald Zou",
            "https://github.com/donaldzou",
        )

    ok_t, text = DashboardConfig.GetConfig("Server", "login_copyright_text")
    ok_u, url = DashboardConfig.GetConfig("Server", "login_copyright_url")
    def_txt, def_url = _defaults()
    if not ok_t or not (str(text).strip()):
        text = def_txt
    if not ok_u or url is None:
        url = def_url
    ok_v, ver = DashboardConfig.GetConfig("Server", "version")
    version_str = str(ver) if ok_v and ver is not None else ""
    text = str(text).replace("{version}", version_str)
    return ResponseObject(data={"text": text, "url": (str(url).strip() if url else "")})


@app.post(f'{APP_PREFIX}/api/savePeerScheduleJob')
def API_savePeerScheduleJob():
    data = request.json
    if "Job" not in data.keys():
        return ResponseObject(False, "Please specify job")
    job: dict = data['Job']
    if "Peer" not in job.keys() or "Configuration" not in job.keys():
        return ResponseObject(False, "Please specify peer and configuration")
    configuration = WireguardConfigurations.get(job['Configuration'])
    if configuration is None:
        return ResponseObject(False, "Configuration does not exist")
    f, fp = configuration.searchPeer(job['Peer'])
    if not f:
        return ResponseObject(False, "Peer does not exist")
    
    
    s, p = AllPeerJobs.saveJob(PeerJob(
        job['JobID'], job['Configuration'], job['Peer'], job['Field'], job['Operator'], job['Value'],
        job['CreationDate'], job['ExpireDate'], job['Action']))
    if s:
        return ResponseObject(s, data=p)
    return ResponseObject(s, message=p)

@app.post(f'{APP_PREFIX}/api/deletePeerScheduleJob')
def API_deletePeerScheduleJob():
    data = request.json
    if "Job" not in data.keys():
        return ResponseObject(False, "Please specify job")
    job: dict = data['Job']
    if "Peer" not in job.keys() or "Configuration" not in job.keys():
        return ResponseObject(False, "Please specify peer and configuration")
    configuration = WireguardConfigurations.get(job['Configuration'])
    if configuration is None:
        return ResponseObject(False, "Configuration does not exist")
    # f, fp = configuration.searchPeer(job['Peer'])
    # if not f:
    #     return ResponseObject(False, "Peer does not exist")

    s, p = AllPeerJobs.deleteJob(PeerJob(
        job['JobID'], job['Configuration'], job['Peer'], job['Field'], job['Operator'], job['Value'],
        job['CreationDate'], job['ExpireDate'], job['Action']))
    if s:
        return ResponseObject(s)
    return ResponseObject(s, message=p)

@app.get(f'{APP_PREFIX}/api/getPeerScheduleJobLogs/<configName>')
def API_getPeerScheduleJobLogs(configName):
    if configName not in WireguardConfigurations.keys():
        return ResponseObject(False, "Configuration does not exist")
    data = request.args.get("requestAll")
    requestAll = False
    if data is not None and data == "true":
        requestAll = True
    return ResponseObject(data=AllPeerJobs.getPeerJobLogs(configName))

'''
Tools
'''

@app.get(f'{APP_PREFIX}/api/ping/getAllPeersIpAddress')
def API_ping_getAllPeersIpAddress():
    ips = {}
    for c in WireguardConfigurations.values():
        cips = {}
        for p in c.Peers:
            allowed_ip = p.allowed_ip.replace(" ", "").split(",")
            parsed = []
            for x in allowed_ip:
                try:
                    ip = ipaddress.ip_network(x, strict=False)
                except ValueError as e:
                    app.logger.error(f"Failed to parse IP address of {p.id} - {c.Name}")
                host = list(ip.hosts())
                if len(host) == 1:
                    parsed.append(str(host[0]))
            endpoint = p.endpoint.replace(" ", "").replace("(none)", "")
            if len(p.name) > 0:
                cips[f"{p.name} - {p.id}"] = {
                    "allowed_ips": parsed,
                    "endpoint": endpoint
                }
            else:
                cips[f"{p.id}"] = {
                    "allowed_ips": parsed,
                    "endpoint": endpoint
                }
        ips[c.Name] = cips
    return ResponseObject(data=ips)

import requests

@app.get(f'{APP_PREFIX}/api/ping/execute')
def API_ping_execute():
    if "ipAddress" in request.args.keys() and "count" in request.args.keys():
        ip = request.args['ipAddress']
        count = request.args['count']
        try:
            if ip is not None and len(ip) > 0 and count is not None and count.isnumeric():
                result = ping(ip, count=int(count), source=None)
                data = {
                    "address": result.address,
                    "is_alive": result.is_alive,
                    "min_rtt": result.min_rtt,
                    "avg_rtt": result.avg_rtt,
                    "max_rtt": result.max_rtt,
                    "package_sent": result.packets_sent,
                    "package_received": result.packets_received,
                    "package_loss": result.packet_loss,
                    "geo": None
                }
                try:
                    r = requests.get(f"http://ip-api.com/json/{result.address}?field=city")
                    data['geo'] = r.json()
                except Exception as e:
                    pass
                return ResponseObject(data=data)
            return ResponseObject(False, "Please specify an IP Address (v4/v6)")
        except Exception as exp:
            return ResponseObject(False, exp)
    return ResponseObject(False, "Please provide ipAddress and count")


@app.get(f'{APP_PREFIX}/api/traceroute/execute')
def API_traceroute_execute():
    if "ipAddress" in request.args.keys() and len(request.args.get("ipAddress")) > 0:
        ipAddress = request.args.get('ipAddress')
        try:
            tracerouteResult = traceroute(ipAddress, timeout=1, max_hops=64)
            result = []
            for hop in tracerouteResult:
                if len(result) > 1:
                    skipped = False
                    for i in range(result[-1]["hop"] + 1, hop.distance):
                        result.append(
                            {
                                "hop": i,
                                "ip": "*",
                                "avg_rtt": "*",
                                "min_rtt": "*",
                                "max_rtt": "*"
                            }
                        )
                        skip = True
                    if skipped: continue
                result.append(
                    {
                        "hop": hop.distance,
                        "ip": hop.address,
                        "avg_rtt": hop.avg_rtt,
                        "min_rtt": hop.min_rtt,
                        "max_rtt": hop.max_rtt
                    })
            try:
                r = requests.post(f"http://ip-api.com/batch?fields=city,country,lat,lon,query",
                                  data=json.dumps([x['ip'] for x in result]))
                d = r.json()
                for i in range(len(result)):
                    result[i]['geo'] = d[i]  
            except Exception as e:
                return ResponseObject(data=result, message="Failed to request IP address geolocation")
            return ResponseObject(data=result)
        except Exception as exp:
            return ResponseObject(False, exp)
    else:
        return ResponseObject(False, "Please provide ipAddress")

@app.get(f'{APP_PREFIX}/api/getDashboardUpdate')
def API_getDashboardUpdate():
    import urllib.request as req
    try:
        repo = resolve_update_github_repo()
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        r = req.urlopen(api_url, timeout=5).read()
        data = dict(json.loads(r))
        tagName = data.get('tag_name')
        htmlUrl = data.get('html_url')
        if tagName is not None and htmlUrl is not None:
            if version.parse(tagName) > version.parse(DashboardConfig.DashboardVersion):
                return ResponseObject(message=f"{tagName} is now available for update!", data=htmlUrl)
            else:
                return ResponseObject(message="You're on the latest version")
        return ResponseObject(False)
    except Exception as e:
        return ResponseObject(False, f"Request to GitHub API failed.")

'''
Sign Up
'''

@app.get(f'{APP_PREFIX}/api/isTotpEnabled')
def API_isTotpEnabled():
    return (
        ResponseObject(data=DashboardConfig.GetConfig("Account", "enable_totp")[1] and DashboardConfig.GetConfig("Account", "totp_verified")[1]))


@app.get(f'{APP_PREFIX}/api/Welcome_GetTotpLink')
def API_Welcome_GetTotpLink():
    if not DashboardConfig.GetConfig("Account", "totp_verified")[1]:
        DashboardConfig.SetConfig("Account", "totp_key", pyotp.random_base32(), True)
        return ResponseObject(
            data=pyotp.totp.TOTP(DashboardConfig.GetConfig("Account", "totp_key")[1]).provisioning_uri(
                issuer_name="WGDashboard"))
    return ResponseObject(False)


@app.post(f'{APP_PREFIX}/api/Welcome_VerifyTotpLink')
def API_Welcome_VerifyTotpLink():
    data = request.get_json()
    totp = pyotp.TOTP(DashboardConfig.GetConfig("Account", "totp_key")[1]).now()
    if totp == data['totp']:
        DashboardConfig.SetConfig("Account", "totp_verified", "true")
        DashboardConfig.SetConfig("Account", "enable_totp", "true")
    return ResponseObject(totp == data['totp'])

@app.post(f'{APP_PREFIX}/api/Welcome_Finish')
def API_Welcome_Finish():
    data = request.get_json()
    if DashboardConfig.GetConfig("Other", "welcome_session")[1]:
        if data["username"] == "":
            return ResponseObject(False, "Username cannot be blank.")

        if data["newPassword"] == "" or len(data["newPassword"]) < 8:
            return ResponseObject(False, "Password must be at least 8 characters")

        updateUsername, updateUsernameErr = DashboardConfig.SetConfig("Account", "username", data["username"])
        updatePassword, updatePasswordErr = DashboardConfig.SetConfig("Account", "password",
                                                                      {
                                                                          "newPassword": data["newPassword"],
                                                                          "repeatNewPassword": data["repeatNewPassword"],
                                                                          "currentPassword": "admin"
                                                                      })
        if not updateUsername or not updatePassword:
            return ResponseObject(False, f"{updateUsernameErr},{updatePasswordErr}".strip(","))

        DashboardConfig.SetConfig("Other", "welcome_session", False)
    return ResponseObject()

class Locale:
    def __init__(self):
        self.localePath = './static/locales/'
        self.activeLanguages = {}
        with open(os.path.join(f"{self.localePath}supported_locales.json"), "r") as f:
            self.activeLanguages = sorted(json.loads(''.join(f.readlines())), key=lambda x : x['lang_name'])
        
    def getLanguage(self) -> dict | None:
        currentLanguage = DashboardConfig.GetConfig("Server", "dashboard_language")[1]
        if currentLanguage == "en":
            return None
        if os.path.exists(os.path.join(f"{self.localePath}{currentLanguage}.json")):
            with open(os.path.join(f"{self.localePath}{currentLanguage}.json"), "r") as f:
                return dict(json.loads(''.join(f.readlines())))
        else:
            return None
    
    def updateLanguage(self, lang_id):
        if not os.path.exists(os.path.join(f"{self.localePath}{lang_id}.json")):
            DashboardConfig.SetConfig("Server", "dashboard_language", "en-US")
        else:
            DashboardConfig.SetConfig("Server", "dashboard_language", lang_id)
        
Locale = Locale()

@app.get(f'{APP_PREFIX}/api/locale')
def API_Locale_CurrentLang():    
    return ResponseObject(data=Locale.getLanguage())

@app.get(f'{APP_PREFIX}/api/locale/available')
def API_Locale_Available():
    return ResponseObject(data=Locale.activeLanguages)
        
@app.post(f'{APP_PREFIX}/api/locale/update')
def API_Locale_Update():
    data = request.get_json()
    if 'lang_id' not in data.keys():
        return ResponseObject(False, "Please specify a lang_id")
    Locale.updateLanguage(data['lang_id'])
    return ResponseObject(data=Locale.getLanguage())

@app.get(f'{APP_PREFIX}/api/email/ready')
def API_Email_Ready():
    return ResponseObject(EmailSender.ready())

@app.post(f'{APP_PREFIX}/api/email/send')
def API_Email_Send():
    data = request.get_json()
    if "Receiver" not in data.keys() or "Subject" not in data.keys():
        return ResponseObject(False, "Please at least specify receiver and subject")
    body = data.get('Body', '')
    subject = data.get('Subject','')
    download = None
    if ("ConfigurationName" in data.keys() 
            and "Peer" in data.keys()):
        if data.get('ConfigurationName') in WireguardConfigurations.keys():
            configuration = WireguardConfigurations.get(data.get('ConfigurationName'))
            attachmentName = ""
            if configuration is not None:
                fp, p = configuration.searchPeer(data.get('Peer'))
                if fp:
                    template = Template(body)
                    download = p.downloadPeer()
                    body = template.render(peer=p.toJson(), configurationFile=download)
                    subject = Template(data.get('Subject', '')).render(peer=p.toJson(), configurationFile=download)
                    if data.get('IncludeAttachment', False):
                        u = str(uuid4())
                        attachmentName = f'{u}.conf'
                        with open(os.path.join('./attachments', attachmentName,), 'w+') as f:
                            f.write(download['file'])   
                        
    
    s, m = EmailSender.send(data.get('Receiver'), subject, body,  
                            data.get('IncludeAttachment', False), (attachmentName if download else ''))
    return ResponseObject(s, m)

@app.post(f'{APP_PREFIX}/api/email/preview')
def API_Email_PreviewBody():
    data = request.get_json()
    subject = data.get('Subject', '')
    body = data.get('Body', '')
    
    if ("ConfigurationName" not in data.keys() 
            or "Peer" not in data.keys() or data.get('ConfigurationName') not in WireguardConfigurations.keys()):
        return ResponseObject(False, "Please specify configuration and peer")
    
    configuration = WireguardConfigurations.get(data.get('ConfigurationName'))
    fp, p = configuration.searchPeer(data.get('Peer'))
    if not fp:
        return ResponseObject(False, "Peer does not exist")

    try:
        template = Template(body)
        download = p.downloadPeer()
        return ResponseObject(data={
            "Body": Template(body).render(peer=p.toJson(), configurationFile=download),
            "Subject": Template(subject).render(peer=p.toJson(), configurationFile=download)
        })
    except Exception as e:
        return ResponseObject(False, message=str(e))

@app.get(f'{APP_PREFIX}/api/systemStatus')
def API_SystemStatus():
    body = SystemStatus.toJson()
    host = body.get("Host")
    if isinstance(host, dict):
        try:
            host["hostname"] = (socket.gethostname() or "").strip()
        except OSError:
            host["hostname"] = ""
        _ok, ep = DashboardConfig.GetConfig("Peers", "remote_endpoint")
        host["peer_remote_endpoint"] = (
            str(ep).strip() if _ok and ep is not None and str(ep).strip() else ""
        )
    return ResponseObject(data=body)

@app.get(f'{APP_PREFIX}/api/protocolsEnabled')
def API_ProtocolsEnabled():
    return ResponseObject(data=ProtocolsEnabled())

'''
OIDC Controller
'''
@app.get(f'{APP_PREFIX}/api/oidc/toggle')
def API_OIDC_Toggle():
    data = request.args
    if not data.get('mode'):
        return ResponseObject(False, "Please provide mode")
    mode = data.get('mode')
    if mode == 'Client':
        DashboardConfig.SetConfig("OIDC", "client_enable", 
                                  not DashboardConfig.GetConfig("OIDC", "client_enable")[1])
    elif mode == 'Admin':
        DashboardConfig.SetConfig("OIDC", "admin_enable",
                                  not DashboardConfig.GetConfig("OIDC", "admin_enable")[1])
    else:
        return ResponseObject(False, "Mode does not exist")
    return ResponseObject()

@app.get(f'{APP_PREFIX}/api/oidc/status')
def API_OIDC_Status():
    data = request.args
    if not data.get('mode'):
        return ResponseObject(False, "Please provide mode")
    mode = data.get('mode')
    if mode == 'Client':
        return ResponseObject(data=DashboardConfig.GetConfig("OIDC", "client_enable")[1])
    elif mode == 'Admin':
        return ResponseObject(data=DashboardConfig.GetConfig("OIDC", "admin_enable")[1])
    return ResponseObject(False, "Mode does not exist")

'''
Client Controller
'''

@app.get(f'{APP_PREFIX}/api/clients/toggleStatus')
def API_Clients_ToggleStatus():
    DashboardConfig.SetConfig("Clients", "enable",
                              not DashboardConfig.GetConfig("Clients", "enable")[1])
    return ResponseObject(data=DashboardConfig.GetConfig("Clients", "enable")[1])


@app.get(f'{APP_PREFIX}/api/clients/allClients')
def API_Clients_AllClients():
    return ResponseObject(data=DashboardClients.GetAllClients())

@app.get(f'{APP_PREFIX}/api/clients/allClientsRaw')
def API_Clients_AllClientsRaw():
    return ResponseObject(data=DashboardClients.GetAllClientsRaw())

@app.post(f'{APP_PREFIX}/api/clients/assignClient')
def API_Clients_AssignClient():
    data = request.get_json()
    configurationName = data.get('ConfigurationName')
    id = data.get('Peer')
    client = data.get('ClientID')
    if not all([configurationName, id, client]):
        return ResponseObject(False, "Please provide all required fields")
    if not DashboardClients.GetClient(client):
        return ResponseObject(False, "Client does not exist")
    
    status, data = DashboardClients.AssignClient(configurationName, id, client)
    if not status:
        return ResponseObject(status, message="Client already assiged to this peer")
    
    return ResponseObject(data=data)

@app.post(f'{APP_PREFIX}/api/clients/unassignClient')
def API_Clients_UnassignClient():
    data = request.get_json()
    assignmentID = data.get('AssignmentID')
    if not assignmentID:
        return ResponseObject(False, "Please provide AssignmentID")
    return ResponseObject(status=DashboardClients.UnassignClient(assignmentID))

@app.get(f'{APP_PREFIX}/api/clients/assignedClients')
def API_Clients_AssignedClients():
    data = request.args
    configurationName = data.get('ConfigurationName')
    peerID = data.get('Peer')
    if not all([configurationName, id]):
        return ResponseObject(False, "Please provide all required fields")
    return ResponseObject(
        data=DashboardClients.GetAssignedPeerClients(configurationName, peerID))

@app.get(f'{APP_PREFIX}/api/clients/allConfigurationsPeers')
def API_Clients_AllConfigurationsPeers():
    c = {}
    for (key, val) in WireguardConfigurations.items():
        c[key] = list(map(lambda x : {
            "id": x.id,
            "name": x.name
        }, val.Peers))
    
    return ResponseObject(
        data=c
    )

@app.get(f'{APP_PREFIX}/api/clients/assignedPeers')
def API_Clients_AssignedPeers():
    data = request.args
    clientId = data.get("ClientID")
    if not clientId:
        return ResponseObject(False, "Please provide ClientID")
    if not DashboardClients.GetClient(clientId):
        return ResponseObject(False, "Client does not exist")
    d = DashboardClients.GetClientAssignedPeersGrouped(clientId)
    if d is None:
        return ResponseObject(False, "Client does not exist")
    return ResponseObject(data=d)

@app.post(f'{APP_PREFIX}/api/clients/generatePasswordResetLink')
def API_Clients_GeneratePasswordResetLink():
    data = request.get_json()
    clientId = data.get("ClientID")
    if not clientId:
        return ResponseObject(False, "Please provide ClientID")
    if not DashboardClients.GetClient(clientId):
        return ResponseObject(False, "Client does not exist")
    
    token = DashboardClients.GenerateClientPasswordResetToken(clientId)
    if token:
        return ResponseObject(data=token)
    return ResponseObject(False, "Failed to generate link")

@app.post(f'{APP_PREFIX}/api/clients/updateProfileName')
def API_Clients_UpdateProfile():
    data = request.get_json()
    clientId = data.get("ClientID")
    if not clientId:
        return ResponseObject(False, "Please provide ClientID")
    if not DashboardClients.GetClient(clientId):
        return ResponseObject(False, "Client does not exist")
    
    value = data.get('Name')
    return ResponseObject(status=DashboardClients.UpdateClientProfile(clientId, value))

@app.post(f'{APP_PREFIX}/api/clients/deleteClient')
def API_Clients_DeleteClient():
    data = request.get_json()
    clientId = data.get("ClientID")
    if not clientId:
        return ResponseObject(False, "Please provide ClientID")
    if not DashboardClients.GetClient(clientId):
        return ResponseObject(False, "Client does not exist")
    return ResponseObject(status=DashboardClients.DeleteClient(clientId))


@app.get(f'{APP_PREFIX}/api/getClientsNetworkOverview')
def API_getClientsNetworkOverview():
    """Rolling 24h Clients statistics (snapshots); see ClientsNetworkOverviewStats."""
    overview = ClientsNetworkOverviewStatsManager.get_overview_for_api()
    overview["interval_ms"] = ClientsNetworkOverviewStats.get_interval_ms(DashboardConfig)
    return ResponseObject(data=overview)

@app.get(f'{APP_PREFIX}/api/webHooks/getWebHooks')
def API_WebHooks_GetWebHooks():
    return ResponseObject(data=DashboardWebHooks.GetWebHooks())

@app.get(f'{APP_PREFIX}/api/webHooks/createWebHook')
def API_WebHooks_createWebHook():
    return ResponseObject(data=DashboardWebHooks.CreateWebHook().model_dump(
        exclude={'CreationDate'}
    ))

@app.post(f'{APP_PREFIX}/api/webHooks/updateWebHook')
def API_WebHooks_UpdateWebHook():
    data = request.get_json()
    status, msg = DashboardWebHooks.UpdateWebHook(data)
    return ResponseObject(status, msg)

@app.post(f'{APP_PREFIX}/api/webHooks/deleteWebHook')
def API_WebHooks_DeleteWebHook():
    data = request.get_json()
    status, msg = DashboardWebHooks.DeleteWebHook(data)
    return ResponseObject(status, msg)

@app.get(f'{APP_PREFIX}/api/webHooks/getWebHookSessions')
def API_WebHooks_GetWebHookSessions():
    webhookID = request.args.get('WebHookID')
    if not webhookID:
        return ResponseObject(False, "Please provide WebHookID")
    
    webHook = DashboardWebHooks.SearchWebHookByID(webhookID)
    if not webHook:
        return ResponseObject(False, "Webhook does not exist")
    
    return ResponseObject(data=DashboardWebHooks.GetWebHookSessions(webHook))
    

'''
Index Page
'''

@app.get(f'{APP_PREFIX}/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    startThreads()
    start_clients_network_overview_scheduler()
    DashboardPlugins.startThreads()
    app.run(host=app_ip, debug=False, port=app_port)