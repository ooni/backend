def dclass(**kw):
    # Faster access than namedtuples and dicts. Prevents unexpected creation
    # of new attrs and access by index and jsonification
    # Could be implemented with dataclass in py3
    class Struct(object):
        __slots__ = list(kw.keys())

        def __repr__(self):
            r = "<dclass"
            for k in self.__slots__:
                r += " {}:{}".format(repr(k), repr(getattr(self, k)))
            return r + ">"

    r = Struct()
    for k, v in kw.items():
        setattr(r, k, v)
    return r
