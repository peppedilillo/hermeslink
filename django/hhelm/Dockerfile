FROM python:3.11-bookworm

# creates directory for project
ENV HOME=/home/app
ENV APP_HOME=/home/app/web
RUN mkdir -p $HOME
RUN mkdir $APP_HOME

# create directory for db
# note that this are mounted, but we are still creating the directory ourself.
# this is because we need to change the ownership of the directory to our app
# user: mounted vols are owned by root.
ENV DB_DIR=/home/app/db/
RUN mkdir $DB_DIR

# create a directory for static files
ENV STATIC_DIR=/home/app/static/staticfiles
RUN mkdir -p $STATIC_DIR
# and one as well for media files
ENV MEDIA_DIR=/home/app/static/mediafiles
RUN mkdir $MEDIA_DIR

WORKDIR $APP_HOME

# do not write pyc file on disk
ENV PYTHONDONTWRITEBYTECODE 1
# do not buffer stdout and stdin
ENV PYTHONUNBUFFERED 1

# install dependencies
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
