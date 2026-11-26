import redis.asyncio as aioredis

from app.api.routers.health import redis_client_kwargs


def _make_connection(url: str):
    # Building a connection is where redis-py rejects TLS options on a plain URL
    # ("unexpected keyword argument 'ssl_cert_reqs'"); no network is used.
    return aioredis.from_url(url, **redis_client_kwargs(url)).connection_pool.make_connection()


def test_plain_redis_url_gets_no_tls_options():
    url = "redis://default:pw@redis.railway.internal:6379"
    assert redis_client_kwargs(url) == {}
    _make_connection(url)


def test_tls_redis_url_keeps_tls_options():
    url = "rediss://default:pw@example.upstash.io:6379"
    assert redis_client_kwargs(url) == {"ssl_cert_reqs": None}
    _make_connection(url)
