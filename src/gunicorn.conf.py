import dashboard
from datetime import datetime
global sqldb, cursor, DashboardConfig, WireguardConfigurations, AllPeerJobs, JobLogger, Dash
bind, app_listen_mode = dashboard.gunicornConfig()
date = datetime.today().strftime('%Y_%m_%d_%H_%M_%S')

def post_worker_init(worker):
    dashboard.startThreads()
    dashboard.start_clients_network_overview_scheduler()
    dashboard.DashboardPlugins.startThreads()

worker_class = 'gthread'
workers = 1
threads = 2
daemon = True
pidfile = './gunicorn.pid'
wsgi_app = "dashboard:app"
accesslog = f"./log/access_{date}.log"
loglevel = "info"
capture_output = True
errorlog = f"./log/error_{date}.log"
pythonpath = "., ./modules"

print(
    f"[Gunicorn] WGDashboard app_listen_mode={app_listen_mode} bind={bind}",
    flush=True,
)
print(f"[Gunicorn] Access log file is at {accesslog}", flush=True)
print(f"[Gunicorn] Error log file is at {errorlog}", flush=True)
