"""Demo login identities used across the API tests.

Kept in a module rather than conftest so test files can import the constants
directly; conftest puts this directory on sys.path.
"""

DEMO_PASSWORD = "demo_change_me"

CITIZEN_A = "ram31@mrittika.demo"      # राम प्रसाद सिंह
CITIZEN_B = "seema32@mrittika.demo"    # सीमा देवी
DEO = "deo@mrittika.demo"
VERIFIER = "lekhpal@mrittika.demo"
TEHSILDAR = "tehsildar@mrittika.demo"

ALL_USERS = [CITIZEN_A, CITIZEN_B, DEO, VERIFIER, TEHSILDAR]

# Read-only stakeholders.
STATE_OFFICER = "state@mrittika.demo"
CENTRAL_OFFICER = "central@mrittika.demo"
SURVEYOR = "survey@mrittika.demo"
RESEARCHER = "research@mrittika.demo"
STAKEHOLDERS = [STATE_OFFICER, CENTRAL_OFFICER, SURVEYOR, RESEARCHER]
