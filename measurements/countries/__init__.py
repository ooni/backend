import os
import json
import threading

from collections import namedtuple

COUNTRY_LIST_FILE = os.path.join(os.path.dirname(__file__), "country-list.json")

Country = namedtuple("Country", ["alpha_2", "name"])


def lazy_load(f):
    def load_if_needed(self, *args, **kw):
        if not self._is_loaded:
            with self._load_lock:
                self._load()
        return f(self, *args, **kw)

    return load_if_needed


class CountryDB(object):
    def __init__(self, filename):
        self.filename = filename
        self._is_loaded = False
        self._load_lock = threading.Lock()

    def _load(self):
        if self._is_loaded:
            return

        self.country_map = {}

        with open(self.filename, "r", encoding="utf-8") as f:
            tree = json.load(f)

        for j in tree:
            alpha2 = j["iso3166_alpha2"].lower()
            if alpha2 in self.country_map:
                raise RuntimeError("Inconsistent country file")
            self.country_map[alpha2] = Country(
                name=j["name"], alpha_2=j["iso3166_alpha2"]
            )

        self._is_loaded = True

    @lazy_load
    def lookup(self, value):
        value = value.lower()
        c = self.country_map.get(value, None)
        if c is None:
            raise KeyError("Could not find a record for %r" % value)
        return c


countries = CountryDB(COUNTRY_LIST_FILE)


def lookup_country(probe_cc):
    return countries.lookup(probe_cc)
