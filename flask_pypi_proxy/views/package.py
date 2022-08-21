# -*- coding: utf-8 -*-

""" Handles downloading a package file.

This is called by easy_install or pip after calling the simple, and getting
the version of the package to download.

"""

from asyncio.log import logger
import fcntl
import time
import magic
from flask import make_response, redirect, request, abort, Response
from urllib.parse import unquote
from flask_pypi_proxy.app import app
from flask_pypi_proxy.utils import (get_base_path, get_package_path,
                                    get_sha256_for_content)
from os import makedirs, remove
from os.path import join, exists
from requests import get, head
from functools import partial


get = partial(get, headers={'User-Agent': 'curl/7.29.0'})


@app.route('/packages/<package_type>/<letter>/<package_name>/<package_file>',
           methods=['GET', 'HEAD'])
def package(package_type, letter, package_name, package_file):
    """ Downloads the egg

    :param str package_type: the nature of the package. For example:
                              'source' or '2.7'
    :param str letter: the first char of the package name. For example:
                              D
    :param str package_name: the name of the package. For example: Django
    :param str package_file: the name of the package and it's version. For
                             example: Django-1.5.0.tar.gz
    """
    egg_filename = join(get_base_path(), package_name, package_file)
    url = unquote(request.args.get('remote'))

    if request.method == 'HEAD':
        # in this case the content type of the file is what is
        # required
        if not exists(egg_filename):
            pypi_response = head(url)
            return _respond(pypi_response.content, pypi_response.headers['content-type'])

        else:
            mimetype = magic.from_file(egg_filename, mime=True)
            return _respond('', mimetype)

    app.logger.debug('Downloading: %s', package_file)
    if exists(egg_filename):
        app.logger.debug('Found local file in repository for: %s', package_file)
        # if the file exists, then use the local file.
        path = get_package_path(package_name)
        path = join(path, package_file)
        with open(path, 'rb') as egg:
            content = egg.read()
        mimetype = magic.from_file(egg_filename, mime=True)
        return _respond(content, mimetype)

    else:
        # Downloads the egg from pypi and saves it locally, then
        # it will return it.
        package_path = get_package_path(package_name)

        if not exists(package_path):
            app.logger.debug('package path is created')
            makedirs(package_path)
	    # Avoid concurrent writing to the file 
        with open(egg_filename, 'wb') as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                app.logger.debug('A BlockingIOError occurs!!!')
                time.sleep(0.5)
                return redirect(request.url)

        # return stream respond
        return _stream_respond(_get_generate(url, package_file, egg_filename), _get_package_length(url))

# make a stream respond
def _stream_respond(filecontent, packagelength):
    return Response(filecontent, content_type="application/octet-stream", headers={"Content-Length": str(packagelength)})

def _respond(filecontent, mimetype):
    return make_response(filecontent, 200, {
                        'Content-Type': mimetype
                    }
            )
# Gets the package size
def _get_package_length(url):
    pypi_response = get(url, stream = True)
    package_length = pypi_response.headers.get('Content-Length')
    pypi_response.close()
    return package_length

# Get chunk generator
def _get_generate(url, package_file, egg_filename):
    # this function is a generator about a HTTP file stream.
    app.logger.debug('Starting to download: %s using the url: %s', package_file, url)
    # get file by streaming
    pypi_response = get(url, stream = True)
    if pypi_response.status_code != 200:
        app.logger.warning('Error respose while downloading for proxy: %s'
                        'Response details: %s', package_file,
                        pypi_response.text)
        abort(pypi_response.status_code)
    # yield data chunk
    try:
        with open(egg_filename, "wb") as egg_file:
            for chunk in pypi_response.iter_content(chunk_size = 1024):
                if chunk:
                    egg_file.write(chunk)
                    yield chunk

        # calc file sha256 and output sha256 to file
        with open(egg_filename + '.sha256', 'w') as sha256_output:
            with open(egg_filename, 'rb') as egg_file:
                filecontent = egg_file.read()
            sha256 = get_sha256_for_content(filecontent)
            sha256_output.write(sha256)
    # if the download fails, delete the incomplete file
    except:
        import traceback
        app.logger.debug(traceback.format_exc())
        remove(egg_filename)
    app.logger.debug('Finished downloading package: %s', package_file)