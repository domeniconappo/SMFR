def test_undertests():
    from smfrcore.utils import UNDER_TESTS
    assert not UNDER_TESTS


def test_mysql():
    from smfrcore.models.sql import TwitterCollection
    res = TwitterCollection.query.all()
    assert len(res) == 1
