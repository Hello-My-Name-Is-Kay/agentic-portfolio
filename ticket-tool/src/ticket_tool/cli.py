"""CLI entry points for the ticket automation tool.

Commands:
  ticket seed     — Seed the database with demo tickets.
  ticket list     — List tickets with optional status/priority filters.
  ticket get      — Get a single ticket by ID.
  ticket create   — Create a new ticket.
  ticket update   — Update a ticket's status/priority/resolution.
  ticket delete   — Delete a ticket.
  ticket audit    — View audit log for a ticket or all tickets.

Usage:
  python -m ticket_tool.cli seed
  python -m ticket_tool.cli list --status open
  python -m ticket_tool.cli get 5
  python -m ticket_tool.cli create --title "Help" --desc "Need help" --customer "John"
  python -m ticket_tool.cli update 1 --status resolved --resolution "Fixed"
  python -m ticket_tool.cli delete 5 --idem-key del-5-abc
  python -m ticket_tool.cli audit --ticket-id 1
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from typing import Any

from ticket_tool.engine import TicketDatabase
from ticket_tool.logging import configure_logging, get_logger
from ticket_tool.models import Ticket, TicketUpdate

log = get_logger("ticket.cli")


def _add_seed_parser(subparsers) -> None:
    p = subparsers.add_parser("seed", help="Seed database with demo tickets")
    p.add_argument("--json", action="store_true", help="Output as JSON for LLM consumption")
    p.set_defaults(func=_cmd_seed)


def _add_list_parser(subparsers) -> None:
    p = subparsers.add_parser("list", help="List tickets")
    p.add_argument("--status", "-s", help="Filter by status")
    p.add_argument("--priority", "-p", help="Filter by priority")
    p.add_argument("--limit", "-l", type=int, default=50, help="Max results")
    p.add_argument("--json", action="store_true", help="Output as JSON for LLM consumption")
    p.set_defaults(func=_cmd_list)


def _add_get_parser(subparsers) -> None:
    p = subparsers.add_parser("get", help="Get ticket by ID")
    p.add_argument("ticket_id", type=int, help="Ticket ID")
    p.add_argument("--json", action="store_true", help="Output as JSON for LLM consumption")
    p.set_defaults(func=_cmd_get)


def _add_create_parser(subparsers) -> None:
    p = subparsers.add_parser("create", help="Create a new ticket")
    p.add_argument("--title", "-t", required=True, help="Ticket title")
    p.add_argument("--description", "-d", required=True, help="Ticket description")
    p.add_argument("--customer", "-c", required=True, help="Customer name")
    p.add_argument("--email", "-e", default="customer@example.com", help="Customer email")
    p.add_argument("--priority", default="medium", help="Priority (low/medium/high/critical)")
    p.add_argument("--category", default="general", help="Category")
    p.add_argument("--idem-key", help="Idempotency key for safe retry")
    p.add_argument("--json", action="store_true", help="Output as JSON for LLM consumption")
    p.set_defaults(func=_cmd_create)


def _add_update_parser(subparsers) -> None:
    p = subparsers.add_parser("update", help="Update a ticket")
    p.add_argument("ticket_id", type=int, help="Ticket ID")
    p.add_argument("--status", help="New status")
    p.add_argument("--priority", help="New priority")
    p.add_argument("--resolution", help="Resolution text")
    p.add_argument("--idem-key", help="Idempotency key for safe retry")
    p.add_argument("--json", action="store_true", help="Output as JSON for LLM consumption")
    p.set_defaults(func=_cmd_update)


def _add_delete_parser(subparsers) -> None:
    p = subparsers.add_parser("delete", help="Delete a ticket")
    p.add_argument("ticket_id", type=int, help="Ticket ID")
    p.add_argument("--idem-key", required=True, help="Idempotency key (required for safety)")
    p.add_argument("--json", action="store_true", help="Output as JSON for LLM consumption")
    p.set_defaults(func=_cmd_delete)


def _add_audit_parser(subparsers) -> None:
    p = subparsers.add_parser("audit", help="View audit log")
    p.add_argument("--ticket-id", "-t", type=int, help="Filter by ticket ID")
    p.add_argument("--limit", "-l", type=int, default=100, help="Max entries")
    p.add_argument("--json", action="store_true", help="Output as JSON for LLM consumption")
    p.set_defaults(func=_cmd_audit)


def _print_json(data: Any) -> None:
    """Pretty-print JSON data."""
    if isinstance(data, list):
        for item in data:
            print(json.dumps({k: str(v) if isinstance(v, datetime) else v for k, v in item.items()}, indent=2))
            print("---")
    elif isinstance(data, dict):
        print(json.dumps({k: str(v) if isinstance(v, datetime) else v for k, v in data.items()}, indent=2))
    else:
        print(data)


def _cmd_seed(args) -> int:
    db = TicketDatabase()
    db.seed_demo_data()
    if args.json:
        print(json.dumps({"status": "ok", "action": "seed", "message": "Database seeded with demo tickets"}))
    else:
        print("✓ Database seeded with demo tickets")
    return 0


def _cmd_list(args) -> int:
    db = TicketDatabase()
    result = db.list_tickets(status=args.status, priority=args.priority, limit=args.limit)
    if result.success:
        if args.json:
            print(json.dumps({"status": "ok", "action": "list", "count": result.affected_rows, "tickets": result.data},
                             indent=2, default=str))
        else:
            print(f"Found {result.affected_rows} ticket(s):\n")
            for t in result.data:
                print(f"  #{t['id']} [{t['status']}/{t['priority']}] {t['title'][:60]}")
                print(f"       {t['customer_name']} — {t['created_at'][:10]}")
    else:
        if args.json:
            print(json.dumps({"status": "error", "reason": result.error}))
        else:
            print(f"Error: {result.error}")
    return 0 if result.success else 1


def _cmd_get(args) -> int:
    db = TicketDatabase()
    result = db.get_ticket(args.ticket_id)
    if result.success:
        if args.json:
            print(json.dumps({"status": "ok", "action": "get", "ticket": result.data}, indent=2, default=str))
        else:
            _print_json(result.data)
    else:
        if args.json:
            print(json.dumps({"status": "error", "reason": result.error}))
        else:
            print(f"Error: {result.error}")
    return 0 if result.success else 1


def _cmd_create(args) -> int:
    ticket = Ticket(
        title=args.title,
        description=args.description,
        customer_name=args.customer,
        customer_email=args.email,
        priority=args.priority,
        category=args.category,
    )
    db = TicketDatabase()
    result = db.create_ticket(ticket, idem_key=args.idem_key)
    if result.success:
        if args.json:
            print(json.dumps({"status": "ok", "action": "create", "ticket": result.data}, indent=2, default=str))
        else:
            print("✓ Ticket created:")
            _print_json(result.data)
    else:
        if args.json:
            print(json.dumps({"status": "error", "reason": result.error}))
        else:
            print(f"Error: {result.error}")
    return 0 if result.success else 1


def _cmd_update(args) -> int:
    update = TicketUpdate(status=args.status, priority=args.priority, resolution=args.resolution)
    db = TicketDatabase()
    result = db.update_ticket(args.ticket_id, update, idem_key=args.idem_key)
    if result.success:
        if args.json:
            print(json.dumps({"status": "ok", "action": "update", "ticket": result.data}, indent=2, default=str))
        else:
            print("✓ Ticket updated:")
            _print_json(result.data)
    else:
        if args.json:
            print(json.dumps({"status": "error", "reason": result.error}))
        else:
            print(f"Error: {result.error}")
    return 0 if result.success else 1


def _cmd_delete(args) -> int:
    db = TicketDatabase()
    result = db.delete_ticket(args.ticket_id, idem_key=args.idem_key)
    if result.success:
        if args.json:
            print(json.dumps({"status": "ok", "action": "delete", "ticket_id": args.ticket_id}))
        else:
            print(f"✓ Ticket {args.ticket_id} deleted")
    else:
        if args.json:
            print(json.dumps({"status": "error", "reason": result.error}))
        else:
            print(f"Error: {result.error}")
    return 0 if result.success else 1


def _cmd_audit(args) -> int:
    db = TicketDatabase()
    result = db.get_audit_log(ticket_id=args.ticket_id, limit=args.limit)
    if result.success:
        if args.json:
            print(json.dumps({"status": "ok", "action": "audit", "count": result.affected_rows, "entries": result.data},
                             indent=2, default=str))
        else:
            print(f"Found {result.affected_rows} audit entries:\n")
            _print_json(result.data)
    else:
        if args.json:
            print(json.dumps({"status": "error", "reason": result.error}))
        else:
            print(f"Error: {result.error}")
    return 0 if result.success else 1


def main(argv: list[str] | None = None) -> int:
    configure_logging(log_level="INFO")

    parser = argparse.ArgumentParser(
        description="Ticket Automation Tool — SQL-driven ticket queue management"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_seed_parser(subparsers)
    _add_list_parser(subparsers)
    _add_get_parser(subparsers)
    _add_create_parser(subparsers)
    _add_update_parser(subparsers)
    _add_delete_parser(subparsers)
    _add_audit_parser(subparsers)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())