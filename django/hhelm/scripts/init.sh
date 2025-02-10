echo "[1/3] Running migrations.."
python manage.py makemigrations accounts
python manage.py makemigrations configs
python manage.py makemigrations main
python manage.py migrate
echo "[2/3] Creating superuser.."
python manage.py createsuperuser
echo "Done"