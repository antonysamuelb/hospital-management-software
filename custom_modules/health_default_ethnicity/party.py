# Site customization for this hospital: GNU Health's stock ethnicity list
# (Black/Asian/White/Hispanic/"Indian American"/Native American — a US
# census-derived list, confirmed by inspecting gnuhealth.ethnicity's seed
# data) has no proper "South Asian" category and defaults to nothing.
# Since almost every patient at this hospital is South Asian, default new
# patients to it rather than leaving every registration to pick it by hand.
#
# Follows the exact same pattern GNU Health's own health.py already uses
# for default_citizenship/default_residence (a staticmethod looking up a
# related record and returning its id) — not inventing a new convention.
from trytond.pool import Pool, PoolMeta

SOUTH_ASIAN_ETHNICITY_CODE = 'SOUTHASIAN'


class Party(metaclass=PoolMeta):
    __name__ = 'party.party'

    @staticmethod
    def default_ethnic_group():
        pool = Pool()
        Ethnicity = pool.get('gnuhealth.ethnicity')
        matches = Ethnicity.search(
            [('code', '=', SOUTH_ASIAN_ETHNICITY_CODE)], limit=1)
        if matches:
            return matches[0].id
        return None
