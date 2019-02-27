import pytest
from disdat.common import DisdatConfig


@pytest.fixture(scope="module", autouse=True)
def initialize():
    config = DisdatConfig.instance()
    try:
        config.init()
    except:
        pass
