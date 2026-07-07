# ratekit

Token-bucket rate limiting for small services.

## Install

    pip install -e .

## Rate limits

The limiter allows a steady rate of requests per minute. When traffic
arrives faster than that, a burst allowance absorbs short spikes. Once
the burst allowance is exhausted, further requests are rejected until
tokens refill over time. The steady rate is one hundred and twenty
requests per minute, and the burst allowance is twenty requests.

Note that the limiter is in-process only: two workers each enforce
their own bucket, so the effective global limit is N workers times the
configured rate — worth knowing before you scale out.

## Development

Run the tests with `python -m pytest`.
