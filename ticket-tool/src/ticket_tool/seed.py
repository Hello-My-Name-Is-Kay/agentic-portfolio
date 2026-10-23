"""Seed data for the ticket database.

Contains demo ticket definitions for development and testing.
All data is synthetic — no real customer information.
"""
from __future__ import annotations

from ticket_tool.models import Ticket

DEMO_TICKETS: list[Ticket] = [
    Ticket(
        title="Cannot login to account",
        description="User gets 'invalid credentials' error since last password change.",
        customer_name="Alice Johnson", customer_email="alice@example.com",
        priority="high", category="account", status="open",
    ),
    Ticket(
        title="Payment not processed",
        description="Credit card charged but booking not confirmed. Transaction ID: TXN-12345.",
        customer_name="Bob Smith", customer_email="bob@example.com",
        priority="critical", category="billing", status="open",
    ),
    Ticket(
        title="Need to extend rental",
        description="Customer wants to extend rental R-00001 by 3 days.",
        customer_name="Charlie Brown", customer_email="charlie@example.com",
        priority="medium", category="reservation", status="in_progress",
    ),
    Ticket(
        title="Wrong vehicle assigned",
        description="Booked a Premium but got Standard at pickup. Location L-0001.",
        customer_name="Diana Prince", customer_email="diana@example.com",
        priority="high", category="fleet", status="open",
    ),
    Ticket(
        title="Invoice request",
        description="Need an invoice for reservation R-00003 for expense reimbursement.",
        customer_name="Eve Adams", customer_email="eve@example.com",
        priority="low", category="billing", status="resolved",
    ),
    Ticket(
        title="GPS not working",
        description="GPS unit in vehicle V-3421 shows 'no signal' since yesterday.",
        customer_name="Frank Castle", customer_email="frank@example.com",
        priority="medium", category="technical", status="open",
    ),
    Ticket(
        title="Add additional driver",
        description="Please add my spouse as an additional driver on reservation R-00002.",
        customer_name="Grace Hopper", customer_email="grace@example.com",
        priority="medium", category="reservation", status="in_progress",
    ),
    Ticket(
        title="Lost key replacement",
        description="Lost the key for vehicle V-4523 at the mall. Need replacement.",
        customer_name="Henry Ford", customer_email="henry@example.com",
        priority="critical", category="operations", status="open",
    ),
]