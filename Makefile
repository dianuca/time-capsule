PYTHON ?= python

.PHONY: run check test migrations migrate

run:
	$(PYTHON) manage.py runserver

check:
	$(PYTHON) manage.py check

test:
	$(PYTHON) manage.py test

migrations:
	$(PYTHON) manage.py makemigrations

migrate:
	$(PYTHON) manage.py migrate