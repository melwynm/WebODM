import os
import socket

from django.core.management.base import BaseCommand
from django.db.models import Q

from app.models import Task
from nodeodm.models import ProcessingNode


def resolve_default_node_hostname(index):
    host = f"webodm_node-odm_{index}"
    try:
        socket.gethostbyname(host)
        return host
    except OSError:
        return host.replace("_", "-")


def sync_default_nodes(count, port=3000):
    count = max(0, int(count or 0))
    synced = []

    for index in range(1, count + 1):
        label = f"node-odm-{index}"
        hostname = resolve_default_node_hostname(index)

        node, _ = ProcessingNode.objects.update_or_create(
            hostname=hostname,
            defaults={
                "hostname": hostname,
                "port": port,
                "label": label,
            },
        )

        legacy_hostnames = {
            f"webodm_node-odm_{index}",
            f"node-odm-{index}",
        }
        if index == 1:
            legacy_hostnames.add("nodeodm")

        stale_nodes = ProcessingNode.objects.filter(port=port).exclude(pk=node.pk).filter(
            Q(label=label) | Q(hostname__in=legacy_hostnames)
        )

        stale_node_ids = list(stale_nodes.values_list("id", flat=True))
        reassigned_tasks = 0
        if stale_node_ids:
            reassigned_tasks = Task.objects.filter(processing_node_id__in=stale_node_ids).exclude(
                processing_node_id=node.pk
            ).update(processing_node=node)
            stale_nodes.delete()

        synced.append(
            {
                "index": index,
                "hostname": hostname,
                "label": label,
                "reassigned_tasks": reassigned_tasks,
                "removed_nodes": len(stale_node_ids),
            }
        )

    return synced


class Command(BaseCommand):
    requires_system_checks = []
    help = "Ensure default NodeODM records match the current Docker hostname and repair legacy aliases."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=int(os.environ.get("WO_DEFAULT_NODES", "0") or 0),
            help="Number of default nodes to synchronize.",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=3000,
            help="Port used by default nodes.",
        )

        super(Command, self).add_arguments(parser)

    def handle(self, **options):
        synced = sync_default_nodes(options.get("count"), port=options.get("port"))
        for item in synced:
            self.stdout.write(
                "synced {label} -> {hostname}:{port} (reassigned {reassigned_tasks}, removed {removed_nodes})".format(
                    port=options.get("port"),
                    **item,
                )
            )
