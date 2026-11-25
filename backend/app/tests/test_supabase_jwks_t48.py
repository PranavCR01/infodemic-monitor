"""T48: verify Supabase asymmetric (ES256/RS256) access tokens against the project's
JWKS, with HS256 + SUPABASE_JWT_SECRET as a fallback. Keys are generated locally and
the JWKS endpoint is faked: no network."""
from __future__ import annotations

import base64
import json
import logging
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from app.auth import dependencies as deps
from app.auth import jwks as jwks_mod
from app.auth.jwks import JWKSCache, _parse_jwks
from app.auth.roles import Role, require_role, role_of
from app.core.config import settings

PROJECT = "https://testproj.supabase.co"
ISSUER = PROJECT + "/auth/v1"
JWKS_URL = ISSUER + "/.well-known/jwks.json"
SECRET = "t48-legacy-secret-not-real-0123456789abcdef"

EC_KEY = ec.generate_private_key(ec.SECP256R1())
EC_KEY_2 = ec.generate_private_key(ec.SECP256R1())
RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_EC_KEY = ec.generate_private_key(ec.SECP256R1())  # not published anywhere


def ec_jwk(priv, kid: str) -> dict:
    d = ECAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    return {**d, "kid": kid, "alg": "ES256", "use": "sig"}


def rsa_jwk(priv, kid: str) -> dict:
    d = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    return {**d, "kid": kid, "alg": "RS256", "use": "sig"}


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def claims(**over) -> dict:
    now = int(time.time())
    c = {"sub": "user-1", "aud": "authenticated", "iss": ISSUER, "role": "authenticated",
         "iat": now, "exp": now + 600, "app_metadata": {"provider": "email"}}
    c.update(over)
    return {k: v for k, v in c.items() if v is not None}


def es256(kid="ec-1", key=EC_KEY, **over) -> str:
    return jwt.encode(claims(**over), key, algorithm="ES256", headers={"kid": kid})


def rs256(kid="rsa-1", key=RSA_KEY, **over) -> str:
    return jwt.encode(claims(**over), key, algorithm="RS256", headers={"kid": kid})


def hs256(secret=SECRET, headers=None, **over) -> str:
    return jwt.encode(claims(**over), secret, algorithm="HS256", headers=headers)


class FakeJWKS:
    """Stands in for the HTTP fetch; counts calls and can fail."""

    def __init__(self, keys):
        self.doc = {"keys": list(keys)}
        self.calls = 0
        self.fail = False
        self.urls = []

    def __call__(self, url):
        self.calls += 1
        self.urls.append(url)
        if self.fail:
            raise ConnectionError("jwks unreachable")
        return json.loads(json.dumps(self.doc))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env(monkeypatch):
    fake = FakeJWKS([ec_jwk(EC_KEY, "ec-1"), rsa_jwk(RSA_KEY, "rsa-1")])
    clock = Clock()
    monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "SUPABASE_URL", PROJECT)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "")
    monkeypatch.setattr(settings, "SUPABASE_JWKS_CACHE_SECONDS", 600)
    monkeypatch.setattr(settings, "SUPABASE_JWKS_MIN_REFETCH_SECONDS", 30)

    def no_network(url):  # any real HTTP fetch is a test bug
        raise AssertionError("network fetch attempted in tests")

    monkeypatch.setattr(jwks_mod, "_http_fetch", no_network)
    cache = JWKSCache(JWKS_URL, ttl=600, min_refetch=30, fetch=fake, clock=clock)
    monkeypatch.setattr(deps, "_jwks_cache", cache)

    app = FastAPI()

    @app.get("/me")
    def me(user: dict = Depends(deps.get_current_user)):
        return {"sub": user.get("sub"), "role": role_of(user).value}

    @app.get("/admin")
    def admin(user: dict = Depends(require_role(Role.ADMIN))):
        return {"ok": True}

    yield {"client": TestClient(app), "fake": fake, "clock": clock, "cache": cache}
    deps.reset_jwks_cache()


def get(env, token, path="/me"):
    return env["client"].get(path, headers={"Authorization": f"Bearer {token}"})


# ------------------------------------------------------------------ accepted tokens


def test_valid_es256_token_is_accepted(env):
    r = get(env, es256())
    assert r.status_code == 200, r.text
    assert r.json() == {"sub": "user-1", "role": "analyst"}
    assert env["fake"].urls == [JWKS_URL]


def test_valid_rs256_token_is_accepted(env):
    assert get(env, rs256()).status_code == 200


def test_jwks_cached_within_ttl_and_refetched_after(env):
    for _ in range(5):
        assert get(env, es256()).status_code == 200
    assert env["fake"].calls == 1
    env["clock"].t += 601
    assert get(env, es256()).status_code == 200
    assert env["fake"].calls == 2


def test_role_still_comes_only_from_app_metadata(env):
    forged = es256(role="admin", user_metadata={"role": "admin"})
    assert get(env, forged).json()["role"] == "analyst"
    assert get(env, forged, "/admin").status_code == 403
    real = es256(app_metadata={"provider": "email", "role": "admin"})
    assert get(env, real).json()["role"] == "admin"
    assert get(env, real, "/admin").status_code == 200


def test_hs256_fallback_when_secret_configured(env, monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    assert get(env, hs256()).status_code == 200
    # Both kinds work side by side during the migration.
    assert get(env, es256()).status_code == 200


def test_key_rotation_new_kid_found_after_refetch(env):
    assert get(env, es256()).status_code == 200            # first fetch
    env["fake"].doc["keys"].append(ec_jwk(EC_KEY_2, "ec-2"))
    env["clock"].t += 31                                   # past the refetch limit
    assert get(env, es256(kid="ec-2", key=EC_KEY_2)).status_code == 200
    assert env["fake"].calls == 2


def test_require_auth_off_is_unchanged(env, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_AUTH", False)
    monkeypatch.setattr(settings, "DEV_USER_ROLE", "reviewer")
    r = env["client"].get("/me")
    assert r.json() == {"sub": "local-dev-user", "role": "reviewer"}
    r = get(env, "garbage")
    assert r.status_code == 200
    assert env["fake"].calls == 0


# ------------------------------------------------------------------ rejections


def test_wrong_kid_is_rejected_after_one_refetch(env):
    assert get(env, es256(kid="nope")).status_code == 401
    assert env["fake"].calls == 1
    # Signed by a real key but labelled with a kid we don't publish: still refused.
    assert get(env, es256(kid="nope", key=OTHER_EC_KEY)).status_code == 401


def test_token_signed_by_unpublished_key_with_real_kid_is_rejected(env):
    assert get(env, es256(kid="ec-1", key=OTHER_EC_KEY)).status_code == 401


def test_unknown_kid_flood_is_rate_limited(env):
    assert get(env, es256()).status_code == 200
    env["clock"].t += 31
    for i in range(50):
        assert get(env, es256(kid=f"bogus-{i}")).status_code == 401
    assert env["fake"].calls == 2  # the initial fetch + one refetch, not 51
    env["clock"].t += 31
    assert get(env, es256(kid="bogus-x")).status_code == 401
    assert env["fake"].calls == 3


def test_expired_token_is_rejected(env):
    r = get(env, es256(exp=int(time.time()) - 5))
    assert r.status_code == 401
    assert r.json()["detail"] == "Token expired"


def test_missing_exp_is_rejected(env):
    assert get(env, es256(exp=None)).status_code == 401


def test_not_yet_valid_token_is_rejected(env):
    assert get(env, es256(nbf=int(time.time()) + 300)).status_code == 401


@pytest.mark.parametrize("aud", ["anon", "service_role", ["other"], None])
def test_wrong_or_missing_audience_is_rejected(env, aud):
    assert get(env, es256(aud=aud)).status_code == 401


@pytest.mark.parametrize("iss", ["https://evil.supabase.co/auth/v1", PROJECT, None])
def test_wrong_or_missing_issuer_is_rejected(env, iss):
    assert get(env, es256(iss=iss)).status_code == 401


def test_hs256_issuer_checked_when_supabase_url_set(env, monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    assert get(env, hs256(iss="https://evil.supabase.co/auth/v1")).status_code == 401
    assert get(env, hs256(aud="anon")).status_code == 401
    assert get(env, hs256(exp=int(time.time()) - 5)).status_code == 401


def test_tampered_signature_is_rejected(env):
    token = es256()
    head, payload, sig = token.split(".")
    raw = bytearray(base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4)))
    raw[5] ^= 0x01
    assert get(env, f"{head}.{payload}.{b64(bytes(raw))}").status_code == 401


def test_tampered_payload_is_rejected(env):
    head, _, sig = es256().split(".")
    evil = b64(json.dumps(claims(app_metadata={"role": "admin"})).encode())
    assert get(env, f"{head}.{evil}.{sig}", "/admin").status_code == 401


def test_rs256_tampered_signature_is_rejected(env):
    head, payload, sig = rs256().split(".")
    raw = bytearray(base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4)))
    raw[-1] ^= 0x01
    assert get(env, f"{head}.{payload}.{b64(bytes(raw))}").status_code == 401


def test_hs256_rejected_when_no_secret_configured(env):
    assert get(env, hs256()).status_code == 401


def test_hs256_with_wrong_secret_is_rejected(env, monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    assert get(env, hs256(secret="another-secret-0123456789abcdef-012345")).status_code == 401


def test_alg_none_is_rejected(env, monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    unsigned = jwt.encode(claims(app_metadata={"role": "admin"}), None, algorithm="none",
                          headers={"kid": "ec-1"})
    assert get(env, unsigned).status_code == 401
    head = b64(json.dumps({"alg": "None", "typ": "JWT", "kid": "ec-1"}).encode())
    body = b64(json.dumps(claims()).encode())
    assert get(env, f"{head}.{body}.").status_code == 401


@pytest.mark.parametrize("alg", ["HS384", "HS512", "ES384", "PS256", "EdDSA"])
def test_other_algorithms_are_rejected(env, monkeypatch, alg):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    head = b64(json.dumps({"alg": alg, "typ": "JWT", "kid": "ec-1"}).encode())
    body = b64(json.dumps(claims()).encode())
    assert get(env, f"{head}.{body}.{b64(b'x' * 64)}").status_code == 401


def _public_forms(priv, jwk):
    pem = priv.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo)
    return [pem, json.dumps(jwk).encode(), json.dumps(jwk, separators=(",", ":")).encode()]


def _hmac_token(secret: bytes, kid: str) -> str:
    # Hand-rolled because PyJWT itself refuses to HMAC with a PEM key.
    import hashlib
    import hmac

    head = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": kid}).encode())
    body = b64(json.dumps(claims(app_metadata={"role": "admin"})).encode())
    sig = hmac.new(secret, f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{b64(sig)}"


@pytest.mark.parametrize("with_secret", [False, True])
def test_algorithm_confusion_hs256_with_public_key_is_rejected(env, monkeypatch, with_secret):
    if with_secret:
        monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    for priv, jwk, kid in [(EC_KEY, ec_jwk(EC_KEY, "ec-1"), "ec-1"),
                           (RSA_KEY, rsa_jwk(RSA_KEY, "rsa-1"), "rsa-1")]:
        for secret in _public_forms(priv, jwk):
            assert get(env, _hmac_token(secret, kid), "/admin").status_code == 401


def test_algorithm_must_match_the_key_type(env):
    # RS256 header pointing at the EC key, and ES256 header pointing at the RSA key.
    assert get(env, rs256(kid="ec-1")).status_code == 401
    assert get(env, es256(kid="rsa-1")).status_code == 401


def test_symmetric_key_in_jwks_is_never_used(env, monkeypatch):
    oct_secret = b"jwks-published-oct-secret-0123456789abcdef"
    env["fake"].doc["keys"].append({"kty": "oct", "kid": "oct-1", "alg": "HS256",
                                    "k": b64(oct_secret)})
    assert get(env, _hmac_token(oct_secret, "oct-1"), "/admin").status_code == 401
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    assert get(env, _hmac_token(oct_secret, "oct-1"), "/admin").status_code == 401
    assert "oct-1" not in env["cache"]._keys


def test_asymmetric_token_without_kid_is_rejected(env):
    token = jwt.encode(claims(), EC_KEY, algorithm="ES256")
    assert get(env, token).status_code == 401
    assert env["fake"].calls == 0


def test_malformed_tokens_are_rejected(env):
    for bad in ["nope", "a.b.c", "a.b", "....", es256() + "x"]:
        assert get(env, bad).status_code == 401
    assert env["client"].get("/me").status_code == 401  # no header at all


def test_asymmetric_token_rejected_without_supabase_url(env, monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(deps, "_jwks_cache", None)
    assert get(env, es256()).status_code == 401


# ------------------------------------------------------------------ fail closed


def test_fail_closed_when_jwks_unreachable_and_nothing_cached(env):
    env["fake"].fail = True
    assert get(env, es256()).status_code == 401
    # The failure is rate-limited too: no retry storm.
    assert get(env, es256()).status_code == 401
    assert env["fake"].calls == 1


def test_stale_cache_used_briefly_when_jwks_unreachable_then_fails_closed(env):
    assert get(env, es256()).status_code == 200
    env["fake"].fail = True
    env["clock"].t += 700                 # stale, inside the 1 h grace
    assert get(env, es256()).status_code == 200
    env["clock"].t += 3600                # well past the grace
    assert get(env, es256()).status_code == 401


def test_rotated_out_key_is_dropped_on_refetch(env):
    assert get(env, es256()).status_code == 200
    env["fake"].doc["keys"] = [rsa_jwk(RSA_KEY, "rsa-1")]
    env["clock"].t += 601
    assert get(env, es256()).status_code == 401


def test_malformed_jwks_fails_closed(env):
    env["fake"].doc = {"not_keys": []}
    assert get(env, es256()).status_code == 401


# ------------------------------------------------------------------ JWKS parsing


def test_parse_keeps_only_asymmetric_signing_keys():
    p256 = ec_jwk(EC_KEY, "ec-ok")
    p384 = ECAlgorithm.to_jwk(ec.generate_private_key(ec.SECP384R1()).public_key(), as_dict=True)
    priv = json.loads(ECAlgorithm.to_jwk(EC_KEY))  # includes "d"
    keys = _parse_jwks({"keys": [
        p256,
        rsa_jwk(RSA_KEY, "rsa-ok"),
        {**p384, "kid": "ec-p384"},
        {**p256, "kid": "enc", "use": "enc"},
        {**p256, "kid": "mislabelled", "alg": "RS256"},
        {**priv, "kid": "private"},
        {"kty": "oct", "kid": "oct", "k": b64(b"s" * 32)},
        {**p256, "kid": ""},
        {"kty": "EC", "crv": "P-256", "kid": "broken", "x": "AA", "y": "AA"},
        "junk",
    ]})
    assert {k: v.algorithm for k, v in keys.items()} == {"ec-ok": "ES256", "rsa-ok": "RS256"}


def test_default_cache_is_built_from_settings(monkeypatch):
    deps.reset_jwks_cache()
    monkeypatch.setattr(settings, "SUPABASE_URL", PROJECT + "/")
    c = deps.get_jwks_cache()
    assert c.url == JWKS_URL and c.ttl == settings.SUPABASE_JWKS_CACHE_SECONDS
    assert deps.get_jwks_cache() is c
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    assert deps.get_jwks_cache() is None
    deps.reset_jwks_cache()


def test_tokens_and_secrets_are_not_logged(env, monkeypatch, caplog):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    caplog.set_level(logging.DEBUG)
    tokens = [es256(kid="bogus"), es256(exp=int(time.time()) - 5), hs256(secret="x" * 40), "a.b.c"]
    for t in tokens:
        assert get(env, t).status_code == 401
    env["fake"].fail = True
    env["clock"].t += 10_000
    get(env, es256())
    text = caplog.text
    for t in tokens:
        assert t not in text
        for part in t.split("."):
            if len(part) > 8:
                assert part not in text
    assert SECRET not in text
    assert env["fake"].doc["keys"][0]["x"] not in text
