import collections
import importlib
import os
import sys
from collections import OrderedDict
from six.moves import configparser
from types import ModuleType
import types
from cafe.drivers.unittest.decorators import DataDrivenClass
from cafe.common.reporting import cclogging


RESERVED_SECTION_NAMES = [
    "defaults",
    "cli-defaults",
]

FIXTURE_ATTR = 'fixture'
DATASETLIST_ATTR = 'dsl'
TESTCLASSES_ATTR = 'test_classes'
BREW_ATTR_LIST = [FIXTURE_ATTR, DATASETLIST_ATTR, TESTCLASSES_ATTR]


class RunFileNotFoundError(Exception):
    pass


class RunFileSectionCollisionError(Exception):
    pass


class RunFileIncompleteBrewError(Exception):
    pass


class MalformedClassImportPathError(Exception):
    pass


class ModuleNotImportableError(Exception):
    pass


class ClassNotImportableError(Exception):
    pass


class BrewMissingTestClassesError(Exception):
    pass


class DuplicateItemException(Exception):
    """Used by _WriteOnceDict"""
    pass


class _WriteOnceDict(OrderedDict):
    """A special dictionary that throws an exception if an attempt to change
    the value of a key is made.
    """
    def __setitem__(self, key, value, dict_setitem=dict.__setitem__):
        if key in self:
            raise DuplicateItemException(
                "Duplicate attribute detected: The '{k}' attribute is"
                " assigned {v} but a duplicate attribute it trying to"
                " overwrite that to {v_new}.".format(
                    k=key, v=self.get(key), v_new=value))
        super(_WriteOnceDict, self).__setitem__(key, value)
        # if key not in self:
        #     root = self.__root
        #     last = root[0]
        #     last[1] = root[0] = self.__map[key] = [last, root, key]
        # return dict_setitem(self, key, value)


class _ImportablePathWrapper(object):
    def __init__(self, class_import_path):
        """Accepts a dotted class path.
        Provides convenience methods for importing module and class object
        denoted by a class_import_path string.
        """
        split_path = class_import_path.rsplit(".", 1)
        if len(split_path) != 2:
            raise MalformedClassImportPathError(
                "Path '{cip}' was malformed.\nA dotted path ending in a "
                "class name was expected.".format(cip=class_import_path))
        self.module_path = split_path[0]
        self.class_name = split_path[1]
        self._original_class_import_path = class_import_path
        self._module = None
        self._class = None

    def __repr__(self):
        s = "{ip}.{cn}".format(ip=self.module_path, cn=self.class_name)
        return s

    def import_module(self):
        """Import the module at import_path and return the module object"""

        if self._module is None:
            try:
                self._module = importlib.import_module(self.module_path)
            except ImportError as ie:
                msg = "Could not import module from path '{p}: {e}".format(
                    p=self.module_path,
                    e=str(ie))
                raise ModuleNotImportableError(msg)
        return self._module

    def import_class(self):
        """Import the module at import_path and extract the class_name class"""
        if self._class is None:
            try:
                self._class = getattr(self.import_module(), self.class_name)
            except AttributeError as err:
                msg = (
                    "Could not import class '{c}' from path '{p}': {e}".format(
                        c=self.class_name,
                        p=self._original_class_import_path,
                        e=str(err)))
                raise ClassNotImportableError(msg)
        return self._class


class _Brew(object):
    def __init__(self, name, fixture, dsl, test_classes):
        self.name = name
        self.fixture = _ImportablePathWrapper(fixture)
        self.dsl = _ImportablePathWrapper(dsl)
        if not test_classes:
            raise BrewMissingTestClassesError(
                "Brew was instantiated without any test classes.")
        if not isinstance(test_classes, collections.Iterable):
            raise BrewMissingTestClassesError(
                "Brew was instantiated with an uniterable test_classes object"
                " of type {t}".format(t=type(test_classes)))
        self.test_classes = [_ImportablePathWrapper(tc) for tc in test_classes]
        self.automodule_name = "{name}_automodule".format(name=self.name)

    def __repr__(self):
        return (
            "\n{name}:\n\t"
            "automodule:  {automodule_name}\n\t"
            "{fixture_attr}:     {fixture}\n\t"
            "{dsl_attr}:         {dsl}\n\t"
            "{testclasses_attr}:\n{tcs}\n".format(
                fixture_attr=FIXTURE_ATTR,
                dsl_attr=DATASETLIST_ATTR,
                testclasses_attr=TESTCLASSES_ATTR,
                name=self.name,
                automodule_name=self.automodule_name,
                fixture=self.fixture,
                dsl=self.dsl,
                tcs='\n'.join(["\t\t{s}{t}".format(
                    s=" " * 5, t=t) for t in self.test_classes])))

    def _generate_module(self, module_name):
        """Create the container module for autgenerated classes."""

        return types.ModuleType(
            module_name,
            "This module was auto-generated as a container for BrewFile-driven"
            " classes generated at runtime.")

    def _register_module(self, module):
        """Add the module to sys.modules so that it's importable elsewhere."""
        sys.modules[module.__name__] = module

    def _generate_test_class(self):
        """
        Create the aggregate test class by generating a new class that inherits
        from the fixture and all the test classes.
        """

        # Import and append the test class objects to the bases list
        bases = list()

        # Make sure the fixture is first in the method resolution order
        bases.append(self.fixture.import_class())

        for tc in self.test_classes:
            bases.append(tc.import_class())

        # Create the new test class from the bases list and register it as a
        # member of the automodule so that it can be properly imported later
        # (type requires that bases be a tuple)

        return type(
            self.name, tuple(bases), {'__module__': self.automodule_name})

    def __call__(self):
        """Generates a module to contain the generated test fixture and
        all data generated test classes.
        Returns the module object"""

        # Generate the automodule and add it to sys.modules
        automodule = self._generate_module(self.automodule_name)
        self._register_module(automodule)

        # Generate the aggregate test class
        test_class = self._generate_test_class()

        # Instantiate the DataDrivenClass decorator with an instance of the
        # dsl_class
        dsl_class = self.dsl.import_class()

        # Generate final data driven class aggregate by decorating the
        # aggregate test_class with the the dsl_class-driven DataDrivenClass
        # decorator.
        ddtest_class = DataDrivenClass(dsl_class())(test_class)

        # Add the ddtest_class to the automodule
        setattr(automodule, ddtest_class.__name__, ddtest_class)

        return automodule


class BrewFile(object):

    def __init__(self, files):
        """Accepts mutiple (config-like) run files and generates a
        consolidated  representation of them, enforcing rules during parsing.

        A BrewFile is a SafeConfigParser file, except:

            The section 'cli-defaults' is special and can only be used for
            defining defaults for optional command-line arguments.
            (NOTE: This feature is not yet implemented)

            All keys in any given section must be unique.

            All section names across all files passed into BrewFile must be
            unique, with the exception of 'defaults' and 'cli-defaults', which
            are special and not vetted.

            The section 'cli-defaults' should only appear once across all
            files passed into BrewFile.
        """

        self._log = cclogging.getLogger(
            cclogging.get_object_namespace(self.__class__))
        self.files = files
        self._data = self._validate_runfiles(files)

    def __repr__(self):
        files = self._files_string()
        brews = self._brews_string()
        return "Files:\n{files}Brews:{brews}".format(files=files, brews=brews)

    @property
    def cli_defaults(self):
        return dict(self._data.items('cli-defaults'))

    def _brews_string(self):
        sub_brews = "\n\t".join(
            ["\n\t".join(str(b).splitlines()) for b in self.iterbrews()])
        return "{brews}\n".format(brews=sub_brews)

    def brews_to_strings(self):
        return self._brews_string().splitlines()

    def _files_string(self):
        return "{files}\n".format(
            files='\n'.join(["{space}{file}".format(
                space="\t", file=f)for f in self.files]))

    def brew_list(self):
        return [
            s for s in self._data.sections()
            if s.lower() not in RESERVED_SECTION_NAMES]

    def iterbrews(self):
        """ Iterates through runfile sections and yields each individual
        section as a Brew object. You have to call .brew() on the individual
        Brews to get them to generate a module that contains the aggregate
        test class, so these should be safe to store in a list regardless of
        dataset size.
        """

        for s in self.brew_list():
            tcs = (
                self._data.get(s, TESTCLASSES_ATTR) or "").strip().splitlines()
            if not tcs:
                continue
            b = _Brew(
                name=s,
                fixture=self._data.get(s, FIXTURE_ATTR),
                dsl=self._data.get(s, DATASETLIST_ATTR),
                test_classes=tcs)
            yield b

    def brew_modules(self):
        """Returns a list of generated modules each with test_classes inside,
        based on the BrewFile's contents.  For a large enough dataset
        this could be memory intensive, so it's recommended to use iterbrews
        and yield the module/test_classes to your runner one at a time.
        """
        modules = list()
        for brew in self.iterbrews():
            module = brew()
            modules.append(module)
        return modules

    @staticmethod
    def _validate_runfiles(files):
        """ Enforces the BrewFile rules on all provided files.
        If all files pass validation, a SafeConfigParser is returned.
        """
        # Validate the config files individually
        for f in files:

            # Make sure the file is actually there since config parser
            # fails silently
            if not os.path.isfile(f):
                msg = "Could not locate file '{f}'".format(f=f)
                raise RunFileNotFoundError(msg)

            # TODO: Add checks for duplicate sections among multiple files
            cfg = configparser.SafeConfigParser()

            # Check for incomplete sections, excluding reserved
            # sections.
            for section in [
                    s for s in cfg.sections()
                    if s not in RESERVED_SECTION_NAMES]:
                for attr in BREW_ATTR_LIST:
                    try:
                        cfg.get(section, attr)
                    except configparser.NoOptionError:
                        msg = (
                            "\nSection '{sec}' in runfile '{filename}' is "
                            "missing the '{attr}' option".format(
                                filename=f, sec=s, attr=attr))
                        raise RunFileIncompleteBrewError(msg)

        # config files are valid, return aggregate config parser object
        # Don't use the _WriteOnceDict for the final returned config
        cfg = configparser.SafeConfigParser(dict_type=OrderedDict)
        cfg.read(files)
        return cfg
