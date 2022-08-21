# -*- coding: utf-8 -*-


""" Gets the list of the packages that can be downloaded.
"""

from urllib.parse import urlparse, urlsplit, urljoin, quote
from collections import namedtuple
from os import listdir
from os.path import join, exists, basename

from bs4 import BeautifulSoup
from flask import abort, render_template
from requests import get
from functools import partial
from flask_pypi_proxy.app import app
from flask_pypi_proxy.utils import (get_package_path, get_base_path,
                                    is_private, url_is_egg_file)


get = partial(get, headers={'User-Agent': 'curl/7.29.0'})
VersionData = namedtuple('VersionData', ['name', 'sha256', 'external_link'])


@app.route('/simple/')
def simple():
    """ Return the template which list all the packages that are installed
    """
    packages = []
    for filename in listdir(get_base_path()):
        packages.append(filename)

    packages.sort()
    return render_template('simple.html', packages=packages)


@app.route('/simple/<package_name>/')
def simple_package(package_name):
    """ Given a package name, returns all the versions for downloading
    that package.

    If the package doesn't exists, then it will call PyPi (CheeseShop).
    But if the package exists in the local path, then it will get all
    the versions for the local package.

    This will take into account if the egg is private or if it is a normal
    egg that was uploaded to PyPi. This is important to take into account
    the version of the eggs. For example, a proyect requires request==1.0.4
    and another package uses request==1.0.3. Then the instalation of the
    second package will fail because it wasn't downloaded an the **request**
    folder only has the 1.0.4 version.

    To solve this problem, the system uses 2 different kinds of eggs:

    * private eggs: are the eggs that you uploaded to the private repo.
    * normal eggs: are the eggs that are downloaded from pypi.

    So the normal eggs will always get the simple page from the pypi repo,
    will the private eggs will always be read from the filesystem.


    :param package_name: the name of the egg package. This is only the
                          name of the package with the version or anything
                          else.

    :return: a template with all the links to download the packages.
    """
    app.logger.debug('Requesting index for: %s', package_name)
    package_folder = get_package_path(package_name)
    if (is_private(package_name) or (
            exists(package_name) and app.config['SHOULD_USE_EXISTING'])):

        app.logger.debug('Found information of package: %s in local repository',
                         package_name)
        package_versions = []
        template_data = dict(
            source_letter=package_name[0],
            package_name=package_name,
            versions=package_versions
        )

        for filename in listdir(package_folder):
            if not filename.endswith('.sha256'):
                # I only read .sha256 files so I skip this egg (or tar,
                # or zip) file
                continue

            with open(join(package_folder, filename)) as sha256_file:
                sha256 = sha256_file.read(-1)

            # remove .sha256 extension
            name = filename[:-4]
            data = VersionData(name, sha256, None)
            package_versions.append(data)

        return render_template('simple_package.html', **template_data)
    else:
        app.logger.debug('Didnt found package: %s in local repository. '
                         'Using proxy.', package_name)
        url = app.config['PYPI_URL'] + 'simple/%s/' % package_name
        response = get(url)

        if response.status_code != 200:
            app.logger.warning('Error while getting proxy info for: %s'
                               'Errors details: %s', package_name,
                               response.text)
            abort(response.status_code)

        if response.history:
            app.logger.debug('The url was redirected')
            # in this case, the request was redirect, so I should also
            # take into account this change. For example, this happens
            # when requesting flask-bcrypt and on Pypi the request is
            # redirected to Flask-Bcrypt
            package_name = urlparse(response.url).path
            package_name = package_name.replace('/simple/', '')
            package_name = package_name.replace('/', '')

        content = response.content
        external_links = set()

        # contains the list of pacges whih where checked because
        # on the link they had the information of
        visited_download_pages = set()
        soup = BeautifulSoup(content, features="html.parser")
        package_versions = []

        for panchor in soup.find_all('a'):
            if panchor.get('rel') and panchor.get('rel')[0] == 'homepage':
                # skip getting information on the project homepage
                continue

            href = panchor.get('href')
            app.logger.debug('Found the link: %s', href)
            if href.startswith('../../packages/'):
                # then the package is hosted on pypi.
                pk_name = basename(href)
                pk_name, sha256_data = pk_name.split('#sha256=')
                pk_name = pk_name.replace('#sha256=', '')

                # remove sha256 part to make the url shorter.
                split_data = urlsplit(href)
                absolute_url = urljoin(url, split_data.path)

                external_link= 'remote=' + quote(absolute_url, safe='')
                data = VersionData(pk_name, sha256_data, external_link)
                package_versions.append(data)
                continue

            parsed = urlparse(href)
            if parsed.hostname:
                # then the package had a full path to the file
                if parsed.hostname == 'pypi.python.org':
                    # then it is hosted on the pypi server, so I change
                    # it to make it a relative url
                    pk_name = basename(parsed.path)
                    if '#sha256=' in parsed.path:
                        pk_name, sha256_data = pk_name.split('#sha256=')
                        pk_name = pk_name.replace('#sha256=', '')
                    else:
                        sha256_data = ''

                    absolute_url = urljoin(url, parsed.path)
                    external_link = 'remote=' + quote(absolute_url)
                    data = VersionData(pk_name, sha256_data, external_link)
                    package_versions.append(data)

                else:
                    # the python package is hosted on another server
                    # that isn't pypi. The packages that doesn't have
                    # rel=download, then they are links to some pages
                    if panchor.get('rel') and panchor.get('rel')[0] == 'download':
                        if url_is_egg_file(parsed.path):
                            external_links.add(href)
                        else:
                            # href point to an external page where the links
                            # to download the package will be found
                            if href not in visited_download_pages:
                                visited_download_pages.add(href)
                                external_links.update(find_external_links(href))

        # after collecting all external links, we insert them in the html page
        for external_url in external_links:
            package_version = basename(external_url)
            existing_value = filter(lambda pv: pv.name == package_version,
                                    package_versions)
            if existing_value:
                # if the package already exists on pypi, then
                # use it's version instead of using the one that is
                # hosted on a remote server
                continue

            external_link = 'remote=' + quote(external_url)
            data = VersionData(package_version, '', external_link)
            package_versions.append(data)

        package_versions.sort(key=lambda v: v.name)

        template_data = dict(
            source_letter=package_name[0],
            package_name=package_name,
            versions=package_versions
        )
        return render_template('simple_package.html', **template_data)


def find_external_links(url):
    """Look for links to files in a web page and returns a set.
    """
    links = set()
    try:
        response = get(url)
        if response.status_code != 200:
            app.logger.warning('Error while getting proxy info for: %s'
                               'Errors details: %s', url,
                               response.text)
        else:
            content_type = response.headers.get('content-type', '')
            if content_type in ('application/x-gzip'):
                # in this case the URL was a redirection to download
                # a package. For example, sourceforge.
                links.add(response.url)
                return links
            if response.content:
                soup = BeautifulSoup(response.content)
                for anchor in soup.find_all('a'):
                    href = anchor.get("href")
                    if url_is_egg_file(href):
                        # href points to a filename
                        if not url.endswith('/'):
                            url += '/'
                        href = get_absolute_url(href, url)
                        links.add(href)
    except:
        # something happened when looking for external links:
        #       timeout, HTML parser error, etc.
        # we must not fail and only log the error
        app.logger.exception('')
    return links


def get_absolute_url(url, root_url):
    """Make relative URLs absolute

    >>> get_absolute_url('/src/blah.zip', 'https://awesome.org/')
    'https://awesome.org/src/blah.zip'
    >>> get_absolute_url('http://foo.bar.org/blah.zip', 'https://awesome.org/')
    'http://foo.bar.org/blah.zip'
    """
    parsed = urlparse(url)
    if url.startswith('//'):
        # this are the URLS parsed from code.google.com
        return 'http:' + url
    elif parsed.scheme:
        return url
    else:
        return urljoin(root_url, parsed.path)