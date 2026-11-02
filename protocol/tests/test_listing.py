import pytest

from webways_protocol import (Identity, ProtocolError, canonical, listing_id, sign_listing,
                            sign_rating, supersedes, verify_listing, verify_rating)

IH = "ab" * 20


def make(ident=None, **kw):
    ident = ident or Identity.generate()
    args = dict(infohash=IH, title="Big Buck Bunny", description="CC-BY film", tags=["film", "cc"],
                license="CC-BY-3.0")
    args.update(kw)
    return ident, sign_listing(ident, **args)


def test_roundtrip_and_stable_id():
    _, doc = make()
    assert verify_listing(doc) == listing_id(doc)
    assert listing_id(doc) == listing_id(dict(reversed(list(doc.items()))))


def test_tamper_detected():
    _, doc = make()
    doc["title"] = "Something else"
    with pytest.raises(ProtocolError):
        verify_listing(doc)


def test_wrong_publisher_detected():
    _, doc = make()
    doc["publisher"] = Identity.generate().public_key
    with pytest.raises(ProtocolError):
        verify_listing(doc)


@pytest.mark.parametrize("patch", [
    {"infohash": "AB" * 20}, {"infohash": "zz" * 20}, {"title": ""}, {"title": "x" * 201},
    {"tags": ["Bad Tag"]}, {"tags": ["a"] * 2}, {"license": "has space"},
    {"price": {"amount": 1.5, "currency": "USD"}}, {"price": {"amount": -1, "currency": "USD"}},
    {"created": 2**40}, {"seq": -1}, {"extra": 1}, {"withdrawn": False},
])
def test_rejects_invalid(patch):
    _, doc = make()
    doc.update(patch)
    with pytest.raises(ProtocolError):
        verify_listing(doc)


def test_v2_infohash_and_price():
    _, doc = make(infohash="cd" * 32, price={"amount": 500, "currency": "USD"})
    verify_listing(doc)


def test_floats_and_bool_ints_rejected():
    with pytest.raises(ProtocolError):
        canonical({"a": 1.0})
    _, doc = make()
    doc["seq"] = True
    with pytest.raises(ProtocolError):
        verify_listing(doc)


def test_supersedes():
    ident, a = make()
    _, b = make(ident, seq=1)
    assert supersedes(b, a) and not supersedes(a, b)


def test_unicode_canonical_is_utf8():
    _, doc = make(title="Café ☕")
    assert "Café ☕".encode() in canonical(doc)
    verify_listing(doc)


def test_rating():
    ident, doc = make()
    r = sign_rating(Identity.generate(), listing_id(doc), 4)
    verify_rating(r)
    r["score"] = 5
    with pytest.raises(ProtocolError):
        verify_rating(r)


def test_key_file_perms(tmp_path):
    p = tmp_path / "k"
    a = Identity.load_or_create(p)
    assert Identity.load_or_create(p).public_key == a.public_key
    assert oct(p.stat().st_mode & 0o777) == "0o600"
