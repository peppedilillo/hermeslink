FROM python:3.11-bookworm

# creates directory for project
ENV HOME=/home/app
ENV APP_HOME=/home/app/web
RUN mkdir -p $HOME
RUN mkdir $APP_HOME

# create a directory for static files
ENV STATIC_DIR=/home/app/static/staticfiles
RUN mkdir -p $STATIC_DIR
# and one as well for media files
ENV MEDIA_DIR=/home/app/static/mediafiles
RUN mkdir $MEDIA_DIR
# finally, one for the email file-backend
ENV EMAIL_DIR=/home/app/emails
RUN mkdir $EMAIL_DIR

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
