# -*- coding: utf-8 -*-

""" Handles the submition of the different packages.

This is used on **register** o **upload**.

For example:

.. code-block:: bash

    python setup.py register
    python setup.py sdist upload


"""

from os import makedirs
from os.path import exists, join

from flask import request
from werkzeug.utils import secure_filename

from flask_pypi_proxy.utils import get_package_path
from flask_pypi_proxy.app import app


@app.route('/pypi/', methods=['POST'])
def index():
    path = get_package_path(request.form['name'])
    if not exists(path):
        makedirs(path)

    if request.files:
        file = request.files['content']
        filename = secure_filename(file.filename)
        file.save(join(path, filename))
        with open(join(path, filename + '.sha256'), 'w') as sha256_file:
            sha256_file.write(request.form['sha256_digest'])
    return 'Registered'
