import os
import socket

from django.core.management.base import BaseCommand
from django.db.models import Q

from app.models import Task
from nodeodm.models import (
    ProcessingNode,
    ProcessingNodeGroupObjectPermission,
    ProcessingNodeUserObjectPermission,
)


def default_node_host_candidates(index):
    candidates = [
        f"webodm_node-odm_{index}",
        f"webodm-node-odm-{index}",
    ]

    if index == 1:
        candidates.extend(["nodeodm", "yamlnodeodm"])

    candidates.append(f"node-odm-{index}")

    seen = set()
    ordered = []
    for candidate in candidates:
        if candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)
    return ordered


def default_node_aliases(index):
    aliases = set(default_node_host_candidates(index))
    if index == 1:
        aliases.update({"nodeodm", "yamlnodeodm"})
    return aliases


def resolve_default_node_hostname(index):
    fallback = f"webodm-node-odm-{index}"
    for host in default_node_host_candidates(index):
        try:
            socket.gethostbyname(host)
            return host
        except OSError:
            continue
    return fallback


def is_default_node_record(node):
    hostname = (node.hostname or "").strip()
    label = (node.label or "").strip()

    return (
        hostname in {"nodeodm", "yamlnodeodm"}
        or hostname.startswith("webodm_node-odm_")
        or hostname.startswith("webodm-node-odm-")
        or hostname.startswith("node-odm-")
        or label.startswith("node-odm-")
    )


def transfer_processing_node_permissions(source_node_ids, target_node):
    if not source_node_ids or target_node is None:
        return 0

    copied = 0

    for permission in ProcessingNodeUserObjectPermission.objects.filter(content_object_id__in=source_node_ids):
        _, created = ProcessingNodeUserObjectPermission.objects.get_or_create(
            user=permission.user,
            permission=permission.permission,
            content_object=target_node,
        )
        if created:
            copied += 1

    for permission in ProcessingNodeGroupObjectPermission.objects.filter(content_object_id__in=source_node_ids):
        _, created = ProcessingNodeGroupObjectPermission.objects.get_or_create(
            group=permission.group,
            permission=permission.permission,
            content_object=target_node,
        )
        if created:
            copied += 1

    return copied


def sync_default_nodes(count, port=3000):
    count = max(0, int(count or 0))
    synced = []
    synced_node_ids = []

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
        synced_node_ids.append(node.pk)

        stale_nodes = ProcessingNode.objects.filter(port=port).exclude(pk=node.pk).filter(
            Q(label=label) | Q(hostname__in=default_node_aliases(index))
        )

        stale_node_ids = list(stale_nodes.values_list("id", flat=True))
        reassigned_tasks = 0
        copied_permissions = 0
        if stale_node_ids:
            copied_permissions = transfer_processing_node_permissions(stale_node_ids, node)
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
                "copied_permissions": copied_permissions,
            }
        )

    removed_extra_nodes = 0
    reassigned_extra_tasks = 0
    copied_extra_permissions = 0

    if synced_node_ids:
        primary_node = ProcessingNode.objects.get(pk=synced_node_ids[0])
        extra_default_nodes = [
            node for node in ProcessingNode.objects.filter(port=port)
            if node.pk not in synced_node_ids and is_default_node_record(node)
        ]
        extra_node_ids = [node.id for node in extra_default_nodes]

        if extra_node_ids:
            copied_extra_permissions = transfer_processing_node_permissions(extra_node_ids, primary_node)
            reassigned_extra_tasks = Task.objects.filter(processing_node_id__in=extra_node_ids).exclude(
                processing_node_id=primary_node.pk
            ).update(processing_node=primary_node)
            ProcessingNode.objects.filter(pk__in=extra_node_ids).delete()
            removed_extra_nodes = len(extra_node_ids)

    if synced:
        synced[0]["removed_nodes"] += removed_extra_nodes
        synced[0]["reassigned_tasks"] += reassigned_extra_tasks
        synced[0]["copied_permissions"] += copied_extra_permissions

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
                "synced {label} -> {hostname}:{port} (reassigned {reassigned_tasks}, removed {removed_nodes}, copied_permissions {copied_permissions})".format(
                    port=options.get("port"),
                    **item,
                )
            )
