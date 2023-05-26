"""
nginx deploy
"""
from io import StringIO

from pyinfra import host
from pyinfra.api.deploy import deploy
from pyinfra.operations import files, server, apt
from pyinfra.facts.deb import DebPackages

def _install_nginx():
    if not host.get_fact(DebPackages):
        raise DeployError(("Can't deploy prerequisites on non-deb system"))

    apt.packages(
        name = "Install nginx-extras",
        packages = ["nginx-extras"],
        _sudo = True,
    )

@deploy("Deploy nginx")
def deploy_nginx():
    _install_nginx()
