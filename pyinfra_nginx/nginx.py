import contextlib
import importlib.resources
from io import StringIO

from pyinfra import host, logger
from pyinfra.operations import files, apt, server, systemd
from pyinfra.facts.deb import DebPackages
from pyinfra_acmetool import deploy_acmetool


def deploy_anubis(**pyinfra_args):
    apt.deb(
        name="install anubis 1.24.0 deb from GitHub",
        src="https://github.com/TecharoHQ/anubis/releases/download/v1.24.0/anubis_1.24.0_amd64.deb",
        **pyinfra_args,
    )
    server.user(
        user="anubis",
        group="www-data",
        **pyinfra_args,
    )
    files.directory(
        path="/var/run/anubis",
        group="www-data",
        mode="770",
        **pyinfra_args,
    )
    systemd_user = files.replace(
        name="Set anubis user in systemd",
        path="/lib/systemd/system/anubis@.service",
        text="DynamicUser=yes",
        replace="User=anubis",
        **pyinfra_args,
    )
    if systemd_user.changed:
        systemd.daemon_reload(**pyinfra_args)


def deploy_nginx(**pyinfra_args):
    if not host.get_fact(DebPackages, **pyinfra_args):
        raise DeployError(("Can't deploy prerequisites on non-deb system"))

    apt.update(cache_time=3600 * 24)

    apt.packages(
        name="Install nginx-extras",
        packages=["nginx-extras"],
    )


@contextlib.contextmanager
def nginx_deployer(reload_nginx: bool = False, anubis=False, **pyinfra_args):
    if anubis:
        deploy_anubis(**pyinfra_args)
    nginx = NGINX(reload_nginx, pyinfra_args)
    yield nginx
    server.shell(
        name=f"Request TLS certificates",
        commands=["acmetool --batch --xlog.severity=debug reconcile"],
        **pyinfra_args
    )
    systemd.service(
        name="enable and start NGINX service",
        service="nginx.service",
        running=True,
        enabled=True,
        reloaded=nginx.reload,
        **pyinfra_args
    )


class NGINX:
    def __init__(self, reload, pyinfra_args):
        self.reload = reload
        self.pyinfra_args = pyinfra_args

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
            anubis=False,
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
        :param anubis: whether anubis should be enabled for the page
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
                reloaded=self.reload,
                **self.pyinfra_args,
            )

        if acmetool:
            deploy_acmetool(
                reload_hook="systemctl reload nginx",
                domains=[domain],
                request_later=True,
                **self.pyinfra_args
            )

        if enabled:
            if config_path:
                config = files.put(
                    src=config_path,
                    dest=f"/etc/nginx/sites-available/{domain}",
                    user="root",
                    group="root",
                    mode="644",
                    **self.pyinfra_args,
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
                    anubis=anubis,
                    **self.pyinfra_args,
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
                    anubis=anubis,
                    **self.pyinfra_args,
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
                    **self.pyinfra_args,
                )
            try:
                self.reload |= config.changed
            except AttributeError:
                logger.error("please pass either webroot, proxy_port, redirect, or config_path to add_nginx_domain")
                raise

        if anubis:
            default_config = (
                f"BIND=/var/run/anubis/{domain}-anubis.sock",
                "BIND_NETWORK=unix",
                "SOCKET_MODE=0666",
                "DIFFICULTY=4",
                "SERVE_ROBOTS_TXT=0",
                f"POLICY_FNAME=/etc/anubis/{domain}.botPolicies.yaml",
                f"TARGET=unix:///var/run/anubis/{domain}-nginx.sock",
            )
            anubis_conf = files.put(
                name=f"Add anubis config for {domain}",
                src=StringIO("\n".join(default_config)),
                dest=f"/etc/anubis/{domain}.env",
                **self.pyinfra_args,
            )
            files.link(
                name=f"Set default anubis policies for {domain}",
                path=f"/etc/anubis/{domain}.botPolicies.yaml",
                target="/usr/share/doc/anubis/botPolicies.yaml",
                **self.pyinfra_args,
            )
            systemd.service(
                service=f"anubis@{domain}.service",
                enabled=enabled,
                running=enabled,
                restarted=anubis_conf.changed,
                **self.pyinfra_args,
            )

        config_link = files.link(
            path=f"/etc/nginx/sites-enabled/{domain}",
            target=f"/etc/nginx/sites-available/{domain}",
            user="root",
            group="root",
            present=enabled,
            **self.pyinfra_args,
        )
        self.reload |= config_link.changed
