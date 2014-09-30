. ./venv/bin/activate
 gunicorn -D --pid gunicorn.pid --error-logfile gunicorn.error.log     --access-logfile gunicorn.acess.log -w 4 -b 0.0.0.0:5000 portal:app
