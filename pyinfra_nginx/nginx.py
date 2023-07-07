"""
nginx deploy
"""
from io import StringIO

from pyinfra import host
from pyinfra.api.deploy import deploy
from pyinfra.operations import files, server, apt, systemd
from pyinfra.facts.deb import DebPackages
from pyinfra_acmetool import deploy_acmetool

def _install_nginx():
    if not host.get_fact(DebPackages):
        raise DeployError(("Can't deploy prerequisites on non-deb system"))

    apt.update(cache_time=3600 * 24)

    apt.packages(
        name = "Install nginx-extras",
        packages = ["nginx-extras"],
        _sudo = True,
    )

def add_nginx_domain(domain: str, config_path: str, enabled=True):
    """Let a domain be handled by nginx, create a Let's Encrypt certificate for it, and deploy the config.

    :param domain: the domain of the website
    :param config_path: the local path to the nginx config file
    :param enabled: whether the site should be enabled at /etc/nginx/sites-enabled
    """
    default_config_link = files.link(
        path="/etc/nginx/sites-enabled/default", present=False
    )
    need_restart = default_config_link.changed

    deploy_acmetool(nginx_hook=True, domains=[domain])

    if enabled:
        config = files.put(
            src=config_path,
            dest=f"/etc/nginx/sites-available/{domain}",
            user="root",
            group="root",
            mode="644",
        )
        config_link = files.link(
            path=f"/etc/nginx/sites-enabled/{domain}",
            target=f"/etc/nginx/sites-available/{domain}",
            user="root",
            group="root",
            present=enabled,
        )
        if config.changed or config_link.changed:
            need_restart = True

    systemd.service(
        name="NGINX should be enabled and running",
        service="nginx.service",
        running=True,
        enabled=True,
        restarted=need_restart,
    )

@deploy("Deploy nginx")
def deploy_nginx():
    _install_nginx()
