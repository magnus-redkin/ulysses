import click
from .seed import seed
from .telemetry import telemetry
from .shield import shield
from .dns import dns
from .reset import reset
from .detect import detect
from .health import health

@click.group()
def brain():
    """Мозг VPN — управление щитами, телеметрией, DNS"""
    pass

brain.add_command(seed)
brain.add_command(telemetry)
brain.add_command(shield)
brain.add_command(dns)
brain.add_command(reset)
brain.add_command(detect)
brain.add_command(health)
