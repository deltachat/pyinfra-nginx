from io import StringIO
import importlib.resources

from pyinfra import host
from pyinfra.api.deploy import deploy
from pyinfra.operations import files, server, apt, systemd
from pyinfra.facts.deb import DebPackages
from pyinfra_acmetool import deploy_acmetool

def deploy_nginx():
    if not host.get_fact(DebPackages):
        raise DeployError(("Can't deploy prerequisites on non-deb system"))

    apt.update(cache_time=3600 * 24)

    apt.packages(
        name = "Install nginx-extras",
        packages = ["nginx-extras"],
    )

def add_nginx_domain(domain: str, config_path: str = None, webroot: str = None, proxy_port: int = None, enabled=True, acmetool=True):
    """Let a domain be handled by nginx, create a Let's Encrypt certificate for it, and deploy the config.

    :param domain: the domain of the website
    :param config_path: the local path to the nginx config file
    :param webroot: path to a webroot directory, e.g. /var/www/staging/. Generates its own config from template.
    :param proxy_port: proxy_pass all HTTP traffic to some internal port
    :param enabled: whether the site should be enabled at /etc/nginx/sites-enabled
    :param acmetool: whether acmetool should fetch TLS certs for the domain
    """
    default_config_link = files.link(
        path="/etc/nginx/sites-enabled/default", present=False
    )
    if default_config_link.changed:
        systemd.service(
            name="reload nginx",
            service="nginx.service",
            reloaded=True,
        )

    if acmetool:
        deploy_acmetool(nginx_hook=True, domains=[domain])

    if enabled:
        if config_path:
            config = files.put(
                src=config_path,
                dest=f"/etc/nginx/sites-available/{domain}",
                user="root",
                group="root",
                mode="644",
            )
        elif webroot:
                config = files.template(
                src=importlib.resources.files(__package__) / "webroot.nginx_config.j2",
                dest=f"/etc/nginx/sites-available/{domain}",
                user="root",
                group="root",
                mode="644",
                webroot=webroot,
                domain=domain,
            )
        elif proxy_port:
            config = files.template(
                src=importlib.resources.files(__package__) / "proxy_pass.nginx_config.j2",
                dest=f"/etc/nginx/sites-available/{domain}",
                user="root",
                group="root",
                mode="644",
                domain=domain,
                proxy_port=proxy_port,
            )
        config_link = files.link(
            path=f"/etc/nginx/sites-enabled/{domain}",
            target=f"/etc/nginx/sites-available/{domain}",
            user="root",
            group="root",
            present=enabled,
        )
        if config.changed or config_link.changed:
            systemd.service(
                name="NGINX should be enabled and running",
                service="nginx.service",
                running=True,
                enabled=True,
                restarted=True,
            )

