import contextlib
import importlib.resources

from pyinfra import host, logger
from pyinfra.operations import files, apt, systemd
from pyinfra.facts.deb import DebPackages
from pyinfra_acmetool import deploy_acmetool


def deploy_nginx():
    if not host.get_fact(DebPackages):
        raise DeployError(("Can't deploy prerequisites on non-deb system"))

    apt.update(cache_time=3600 * 24)

    apt.packages(
        name="Install nginx-extras",
        packages=["nginx-extras"],
    )


@contextlib.contextmanager
def nginx_deployer(reload_nginx: bool = False):
    nginx = NGINX(reload_nginx)
    yield nginx
    systemd.service(
        name="enable and start NGINX service",
        service="nginx.service",
        running=True,
        enabled=True,
        reloaded=nginx.reload,
    )


class NGINX:
    def __init__(self, reload):
        self.reload = reload

    def add_nginx_domain(
            self,
            domain: str,
            config_path: str = None,
            webroot: str = None,
            proxy_port: int = None,
            redirect: str = None,
            enabled=True,
            acmetool=True,
            websocket_support=False,
    ) -> bool:
        """Let a domain be handled by nginx, create a Let's Encrypt certificate for it, and deploy the config.

        This method supports 3 template configs for configuring your site:
        - "webroot" for serving a static page,
        - "proxy_port" for passing traffic to a separate application listening on some port,
        - and "redirect" for redirecting to a different website with a 301 HTTP status code.
        - You can use "config_path" if your site is so special it needs a custom config.
        These 4 options are mutually exclusive.

        :param domain: the domain of the website
        :param config_path: the local path to the nginx config file
        :param webroot: path to a webroot directory, e.g. /var/www/staging/. Generates its own config from template.
        :param proxy_port: proxy_pass all HTTP traffic to some internal port
        :param redirect: where to 301 redirect to, e.g. https://i.delta.chat$request_uri
        :param enabled: whether the site should be enabled at /etc/nginx/sites-enabled
        :param acmetool: whether acmetool should fetch TLS certs for the domain
        :param websocket_support: whether websockets should be supported (with proxy_port only for now)
        :return whether the nginx config was changed and needs a reload
        """
        default_config_link = files.link(
            path="/etc/nginx/sites-enabled/default", present=False
        )
        if default_config_link.changed:
            systemd.service(
                name="enable and start NGINX service",
                service="nginx.service",
                running=True,
                enabled=True,
                reloaded=nginx.reload,
            )


        if acmetool:
            deploy_acmetool(reload_hook="systemctl reload nginx", domains=[domain])

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
                if websocket_support:
                    websocket_config = '''proxy_set_header\tUpgrade $http_upgrade;
        proxy_set_header\tConnection "upgrade";
        proxy_read_timeout\t86400;'''
                else:
                    websocket_config = ''
                config = files.template(
                    src=importlib.resources.files(__package__)
                        / "proxy_pass.nginx_config.j2",
                    dest=f"/etc/nginx/sites-available/{domain}",
                    user="root",
                    group="root",
                    mode="644",
                    domain=domain,
                    proxy_port=proxy_port,
                    websocket_config=websocket_config,
                )
            elif redirect:
                config = files.template(
                    src=importlib.resources.files(__package__) / "redirect.nginx_config.j2",
                    dest=f"/etc/nginx/sites-available/{domain}",
                    user="root",
                    group="root",
                    mode="644",
                    domain=domain,
                    redirect=redirect,
                )
            try:
                self.reload |= config.changed
            except AttributeError:
                logger.error("please pass either webroot, proxy_port, redirect, or config_path to add_nginx_domain")
                raise

        config_link = files.link(
            path=f"/etc/nginx/sites-enabled/{domain}",
            target=f"/etc/nginx/sites-available/{domain}",
            user="root",
            group="root",
            present=enabled,
        )
        self.reload |= config_link.changed
