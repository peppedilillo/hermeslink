# Hermes Link

This is web application designed to enable communication between the HERMES-Pathfinder nanosatellite constellation Mission and Science operation center.
The applications lives at https://hermeslink.ssdc.asi.it/.
It was realized in python Django, and embeds a grafana dashboard service.

## Running Hermes Link

### Development

Start docker:

```
docker compose build
docker compose up
```

Sets the dotfiles. Samples are provided as `sample.*.env` files or `sample.*.env.prod` files.

```shell
cp sample.django.env .django.env
vim .django.env # fill
... # repeat for other dotfiles
```

Check the container name for the hermeslink-web service, get a shell and create a superuser:

```shell
docker exec -it hermeslink-web bash
python manage.py createsuperuser
```

### Production:

```
docker compose -f compose.prod.yml build
docker compose -f compose.prod.yml up
```

## Commands

To show the welcome message, run:

```
python manage.py say_hi
```

## Utilities

### Test user

To add test users, run:

```python
python manage.py create_users userfile.txt
```

See `accounts/management/commands/create_users.py` for more informations.

### Test configurations

