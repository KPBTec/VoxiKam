# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Dobles de prueba para AsyncSession, usados por los tests de caracterización
de facturación (tests/test_calc_bill.py, tests/test_ingest_cdr.py).

FakeSession matchea cada .execute() por CONTENIDO (substring del SQL +
claves de los params) en vez de una cola posicional — una cola se rompe en
cuanto el código bajo test agrega/reordena una query que no toca el camino
que el test le importa; matchear por contenido es igual de determinístico y
no es frágil a eso.
"""


class FakeRow:
    """Fila que soporta tanto row[0] (tupla) como row["col"] (mapping) —
    los dos estilos de acceso que usa el código real según llame
    .execute(...).first() directo o .execute(...).mappings().first()."""

    def __init__(self, **kwargs):
        self._d = kwargs

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self._d.values())[key]
        return self._d[key]

    def __repr__(self):
        return f"FakeRow({self._d!r})"


class FakeResult:
    def __init__(self, rows, rowcount=None):
        self._rows = list(rows)
        # Para UPDATE/DELETE sin filas de retorno: por default se asume que
        # afectó 1 fila (el caso común "el UPDATE condicional encontró y
        # actualizó la fila") — pasar rowcount=0 explícito para simular el
        # caso "otro proceso ya la actualizó" que estos guards atómicos cubren.
        self.rowcount = rowcount if rowcount is not None else 1

    def first(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar(self):
        if not self._rows:
            return None
        row = self._rows[0]
        return row[0] if isinstance(row, FakeRow) else row


class WithRowcount:
    """Envoltorio explícito para especificar rowcount en un UPDATE/DELETE
    simulado — a propósito NO es una tupla (rows, rowcount) plana, porque
    varios tests ya usan tuplas vacías `()` como forma de decir "sin filas"
    para SELECTs, y esas se confundirían con este caso si el chequeo fuera
    solo "es una tupla"."""
    __slots__ = ("rows", "rowcount")

    def __init__(self, rows, rowcount):
        self.rows = rows
        self.rowcount = rowcount


class FakeSession:
    def __init__(self, routes):
        """routes: lista de (predicate(sql, params) -> bool, spec), donde spec es
        una lista/tupla de rows, un WithRowcount(rows, rowcount), o un callable
        que devuelve cualquiera de esas dos formas."""
        self.routes = routes
        self.calls = []  # [(sql, params)], para asserts sobre qué se ejecutó
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        params = params or {}
        self.calls.append((sql, params))
        for predicate, spec in self.routes:
            if predicate(sql, params):
                resolved = spec() if callable(spec) else spec
                if isinstance(resolved, WithRowcount):
                    return FakeResult(resolved.rows, rowcount=resolved.rowcount)
                return FakeResult(resolved)
        return FakeResult([])

    async def commit(self):
        self.committed = True

    def sql_calls_matching(self, substring: str):
        return [(sql, params) for sql, params in self.calls if substring in sql]


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))
