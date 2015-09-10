# Copyright 2015 Rackspace
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import os
from datetime import datetime
from six.moves import configparser

from cafe.configurator.managers import OPENCAFE_SUB_DIRS, ENGINE_CONFIG_PATH


class EngineDataSource(object):
    def __init__(self, config_file_path, section_name):
        self._data_source = configparser.SafeConfigParser()
        self._section_name = section_name
        self._data_source.read(config_file_path)

    def get(self, item_name, default=None):
        match = 'CAFE_{0}_'.format(self._section_name)
        env_vars = {k[len(match):]: v for k, v in os.environ.iteritems()
                    if k.startswith(match)}
        try:
            return self._data_source.get(
                self._section_name, item_name, raw=True, vars=env_vars)
        except:
            return default


class EngineConfig(object):
    SECTION_NAME = "ENGINE"
    TIME = datetime.now()

    def __init__(self):
        self._data_source = EngineDataSource(
            ENGINE_CONFIG_PATH, self.SECTION_NAME)
        self._format_vars = {
            "test_config": self._get("test_config"),
            "timestamp": self.TIME.strftime("%Y-%m-%d_%H_%M_%S.%f"),
            "unix_timestamp": int((
                self.TIME - datetime(1970, 1, 1)).total_seconds())}

    def _get(self, item_name, default=None):
        return self._data_source.get(item_name, default)

    def _get_path(self, path):
        return os.path.abspath(os.path.expanduser(path))

    @property
    def config_directory(self):
        """
        Provided as the default location for test config files.
        """
        return self._get_path(
            self._get("config_directory", OPENCAFE_SUB_DIRS.CONFIG_DIR))

    @property
    def data_directory(self):
        """
        Provided as the default location for data required by tests.
        """

        return self._get_path(self._get(
            "data_directory", OPENCAFE_SUB_DIRS.DATA_DIR))

    @property
    def log_directory(self):
        """
        Provided as the default location for logs.
        It is recommended that the default log directory be used as a root
        directory for subdirectories of logs.
        """
        return self._get_path(self._get(
            "log_directory", OPENCAFE_SUB_DIRS.LOG_DIR))

    @property
    def logging_verbosity(self):
        """
        Used by the engine to determine which loggers to add handlers to by
        default
        """
        return self._get("logging_verbosity", "STANDARD")

    @property
    def master_log_file_name(self):
        """
        Used by the engine logger as the default name for the file written
        to by the handler on the root python log (since the root python logger
        doesn't have a name by default).
        """
        return self._get("master_log_file_name", "cafe.master").format(
            **self._format_vars)

    @property
    def root_log_dir(self):
        root = self._get("root_log_dir", "{test_config}").format(
            **self._format_vars)
        return os.path.join(self.log_directory, root)

    @property
    def temp_directory(self):
        """
        Provided as the default location for temp files and other temporary
        output generated by tests (not for logs).
        """
        return self._get_path(self._get(
            "temp_directory", OPENCAFE_SUB_DIRS.TEMP_DIR))

    @property
    def test_config(self):
        relative_path = self._get("test_config", os.devnull)
        return os.path.join(self.config_directory, relative_path)

    @property
    def test_log_dir(self):
        relative_path = self._get("test_log_dir", "{timestamp}").format(
            **self._format_vars)
        return os.path.join(self.root_log_dir, relative_path)

    @property
    def default_test_repo(self):
        """
        Provided as the default name of the python package containing tests to
        be run.  This package must be in your python path under the name
        provided here.
        """
        return self._get("default_test_repo", "cloudroast")
