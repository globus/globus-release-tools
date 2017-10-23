# Copyright 2014-2015 University of Chicago
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Package to manage the Globus Toolkit Debian repositories
"""

import os
import re
import subprocess

import repo
import repo.package

default_codenames = ['squeeze', 'wheezy', 'lucid', 'precise', 'trusty']
default_arches = ['i386', 'amd64', 'source']
codename_re = re.compile(r"Codename:\s*(\S+)")
distro_re = re.compile(r"Distribution:\s*(\S+)")


class Repository(repo.Repository):
    """
    repo.deb.Repository
    ===================
    This class contains the debian package repository metadata. It extends the
    repo.Repository class with support code to parse debian package metadata
    from the release's Sources.gz file
    """

    def __init__(self, repo_path, codename, arch, release):
        super(Repository, self).__init__()
        self.repo_path = repo_path
        self.codename = codename
        self.release = release
        self.dirty = False

        if arch == 'source' or arch == 'all':
            cmd = [
                'aptly',
                '-config', os.path.join(self.repo_path, 'aptly.conf'),
                '--format',
                '{{.Package}}|{{.Version}}|{{.Architecture}}|{{.Source}}',
                'repo', 'search', '{0}-{1}'.format(codename, release),
                '$Architecture (=source)']
            pkglist = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            out, err = pkglist.communicate()
        else:
            cmd = [
                'aptly',
                '-config', os.path.join(self.repo_path, 'aptly.conf'),
                '--format',
                '{{.Package}}|{{.Version}}|{{.Architecture}}|{{.Source}}',
                'repo', 'search', '{0}-{1}'.format(codename, release),
                '$Architecture (={0})'.format(arch)]
            pkglist = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            out, err = pkglist.communicate()

        for line in out.split("\n"):
            name = None
            source = None
            version = None
            release = None
            pkgarch = None
            line = line.rstrip()
            if line == '':
                continue

            name, version, pkgarch, source = line.split("|")

            if ':' in version:
                version, release = version.strip().split(": ")[1].split("-", 1)
            else:
                version, release = version.strip().split("-", 1)
            if name not in self.packages:
                self.packages[name] = []

                if arch == 'source':
                    source = name
                    src = source
                    self.packages[name].append(
                            repo.package.Metadata(
                                name,
                                version,
                                release,
                                '{0}_{1}-{2}.dsc'.format(
                                    name,
                                    version,
                                    release),
                                'src',
                                src,
                                '{0}-{1}'.format(self.codename, self.release)))
                else:
                    if source is None or source == '<no value>':
                        source = name
                    src = source
                    self.packages[name].append(
                            repo.package.Metadata(
                                name,
                                version,
                                release,
                                '{0}_{1}-{2}_{3}.deb'.format(
                                    name,
                                    version,
                                    release,
                                    pkgarch),
                                pkgarch,
                                src,
                                '{0}-{1}'.format(self.codename, self.release)))

        for n in self.packages:
            self.packages[n].sort()

    def add_package(self, package, update_metadata=False):
        """
        Add *package* to this repository, optionally regenerating the
        metadata. If update_metadata is equal to False (the default), then
        the repository will be marked as dirty, but the update will not be
        done.

        Parameters
        ----------
        *package*::
            The package to add to this repository
        *update_metadata*::
            Flag indicating whether to update the repository metadata
            immediately or not.
        """
        if package.path.endswith("changes"):
            cmd = [
                'aptly',
                '-config', os.path.join(self.repo_path, 'aptly.conf'),
                '--no-remove-files=true',
                '--repo={0}'.format(self.codename),
                'repo', 'include', package.path,
            ]
            subprocess.Popen(cmd).communicate()
        else:
            if package.arch == 'src':
                cmd = [
                    'aptly',
                    '-config', os.path.join(self.repo_path, 'aptly.conf'),
                    'repo',
                    '-with-deps',
                    '-dep-follow-source',
                    'copy',
                    package.os,
                    '{0}-{1}'.format(self.codename, self.release),
                    '$Source ({0}), $SourceVersion (= {1}-{2})'.format(
                        package.source_name,
                        package.version.strversion,
                        package.version.release),
                ]
                subprocess.Popen(cmd).communicate()
            else:
                cmd = [
                    'aptly',
                    '-config', os.path.join(self.repo_path, 'aptly.conf'),
                    'repo',
                    'copy',
                    package.os,
                    '{0}-{1}'.format(self.codename, self.release),
                    '{0} (= {1}-{2}) {{{3}}}'.format(
                        package.name,
                        package.version.strversion,
                        package.version.release,
                        package.arch),
                ]
                subprocess.Popen(cmd).communicate()

        if update_metadata:
            self.update_metadata()
        else:
            self.dirty = True

        # Create a new repo.package.Metadata with the new path
        new_package = repo.package.Metadata(
                package.name,
                package.version.strversion, package.version.release,
                package.path,
                package.arch,
                package.source_name,
                self.codename)

        if package.name not in self.packages:
            self.packages[package.name] = []
        self.packages[package.name].append(new_package)
        self.packages[package.name].sort()
        if update_metadata:
            self.update_metadata()
        else:
            self.dirty = True
        return new_package

    def update_metadata(self, force):
        """
        Update the package metadata from the changes files in a repository
        """
        if self.dirty or force:
            cmd = [
                'aptly',
                '-config', os.path.join(self.repo_path, 'aptly.conf'),
                'publish',
                'update',
                self.codename,
                self.release,
            ]
            subprocess.Popen(cmd).communicate()
            self.dirty = False
            self.create_index(self.repo_path, recursive=True)


class Release(repo.Release):
    def __init__(
            self, name, topdir, codenames=default_codenames,
            arches=default_arches):
        r = {}
        for codename in codenames:
            r[codename] = {}
            for arch in arches:
                if arch == 'source':
                    r[codename]['src'] = Repository(
                        topdir, codename, arch, name)
                else:
                    r[codename][arch] = Repository(
                        topdir, codename, arch, name)
        super(Release, self).__init__(name, r)

    def repositories_for_package(self, package):
        """
        Returns a list of repositories where the given package would belong.
        By default, its a list containing the repository that matches the
        package's os and arch, but subclasses can override this
        """
        repoarch = package.arch
        if package.arch == 'all':
            repoarch = 'src'
        osname = package.os.split('-')[0]
        if osname in self.repositories:
            return [self.repositories[osname][repoarch]]
        else:
            return []

    def update_metadata(self, osname=None, arch=None, force=False):
        for repository in self.repositories:
             r = self.repositories[repository]
             r[r.keys()[0]].update_metadata(force)

class Manager(repo.Manager):
    """
    Package Manager
    ===============
    The repo.deb.Manager object manages the packages in a release
    tree. New packages from the repositories can be
    promoted to any of the released package trees via methods in this class
    """
    def __init__(
            self, root=repo.default_root,
            releases=repo.default_releases, os_names=None,
            exclude_os_names=None):
        """
        Constructor
        -----------
        Create a new Manager object.

        Parameters
        ----------
        *root*::
            Root of the release trees
        *releases*::
            Names of the releases within the release trees
        *os_names*::
            (Optional) List of operating system codenames (e.g. wheezy) to
            manage. If None, then all debian-based OSes will be managed.
        *exclude_os_names*::
            (Optional) List of operating system codenames (e.g. wheezy) to
            skip. If None, then all debian-based OSes will be managed. This is
            evaluated after os_names
        """
        deb_releases = {}

        codenames = Manager.find_codenames(root, releases[0])

        if os_names is not None:
            codenames = [cn for cn in codenames if cn in os_names]
        if exclude_os_names is not None:
            codenames = [cn for cn in codenames if cn not in exclude_os_names]
        for release in releases:
            deb_releases[release] = Release(
                    release,
                    os.path.join(root, 'aptly'),
                    codenames)
        super(Manager, self).__init__(deb_releases)

    @staticmethod
    def find_codenames(root, release):
        codenames = []

        if os.path.exists(root):
            aptly = subprocess.Popen([
                'aptly',
                '-config', os.path.join(root, 'aptly', 'aptly.conf'),
                '--raw', 'repo', 'list'],
                stdout=subprocess.PIPE)
            out, err = aptly.communicate()
            codenames = [
                x for x in list(
                set(repo.split('-')[0] for repo in out.split("\n")))
                if x != '']
        return codenames

    def __str__(self):
        return " ".join(["Deb Manager [", ",".join(self.releases.keys()), "]"])

# vim: filetype=python:
