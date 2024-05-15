# pyinfra-nginx

This is a pyinfra module to manage an nginx web server.

## Install

Just install this python package with
`pip install git+https://git.0x90.space/0x90/pyinfra-nginx/`
(preferably to your virtual environment).

## Usage

You can use this module
from your pyinfra deploy.py file
like this:

```
from pyinfra_nginx import deploy_nginx, nginx_deployer


deploy_nginx()  # install nginx via apt if it doesn't exist

with nginx_deployer() as n:
    n.add_nginx_domain(domain="example.org", webroot="/var/www/html/")
```

This will install nginx via apt
(only Debian-like systems are supported right now)
and deploy an example nginx config
which exposes static files
under the `/var/www/html` directory.

### Options

`add_nginx_domain()` supports 3 template configs for configuring your site:

- `webroot` for serving a static page,
- `proxy_port` for passing traffic to a separate application listening on some port,
- and `redirect` for redirecting to a different website with a 301 HTTP status code.
- You can use `config_path` if your site is so special it needs a custom config.

These 4 options are mutually exclusive.

