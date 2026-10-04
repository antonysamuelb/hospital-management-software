from trytond.pool import Pool

from . import party


def register():
    Pool.register(
        party.Party,
        module='health_default_ethnicity', type_='model')
