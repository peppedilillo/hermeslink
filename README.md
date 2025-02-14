For production:
`docker compose -f compose.prod.yml build`
`docker compose -f compose.prod.yml up`
The website should be accessible at `http://localhost:1337/

For development:
`docker compose build`
`docker compose up`
The website should be accessible at `http://localhost:8000/`

Based on [this](https://testdriven.io/blog/dockerizing-django-with-postgres-gunicorn-and-nginx/) guide.
I still don't understand fully what the server reverse proxy settings are doing. 
Note I expect them to interact with the django app setting `CSRF_TRUSTED_ORIGINS`.

Repomix:
`repomix --ignore="**/migrations/ .`