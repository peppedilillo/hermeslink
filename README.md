# Hermes Link

This is web application designed to enable communication between the HERMES-Pathfinder nanosatellite constellation Mission and Science operation center.
It is realized in python Django, and embeds a grafana dashboard service.

### Running Hermes Link

For production:
```
docker compose -f compose.prod.yml build
docker compose -f compose.prod.yml up
```

For development:
```
docker compose build
docker compose up
```

Both environment requires the settings of a number of dot files. Samples are provided as `sample.*.env` files or `sample.*.env.prod` files.

### Commands

To show the welcome message, run:

```
python manage.py say_hi
```

To add users, run:

```python
python manage.py create_users userfile.txt
```

See `accounts/management/commands/create_users.py` for more informations.