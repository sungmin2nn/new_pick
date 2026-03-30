"""
BNF Position Manager

Multi-day position tracking system with state management, risk controls,
and JSON persistence for BNF (Breakthrough News Factor) trading.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Any


class PositionState(Enum):
    """Position lifecycle states"""
    PENDING = "pending"           # Selected but not entered
    PARTIAL = "partial"           # Partially filled (split entry in progress)
    FULL = "full"                 # Fully entered
    EXITING = "exiting"           # Split exit in progress
    CLOSED = "closed"             # Fully exited


@dataclass
class Position:
    """
    Represents a trading position with multi-day tracking capability.

    Attributes:
        code: Stock code (e.g., '005930')
        name: Stock name (e.g., '삼성전자')
        state: Current position state
        entries: List of entry transactions
        exits: List of exit transactions
        current_price: Latest price for P&L calculation
        unrealized_pnl: Current unrealized profit/loss
        created_at: Position creation timestamp
        updated_at: Last update timestamp
    """
    code: str
    name: str
    state: PositionState
    entries: List[Dict[str, Any]] = field(default_factory=list)
    exits: List[Dict[str, Any]] = field(default_factory=list)
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def get_total_entry_quantity(self) -> int:
        """Calculate total entered quantity"""
        return sum(entry['quantity'] for entry in self.entries)

    def get_total_exit_quantity(self) -> int:
        """Calculate total exited quantity"""
        return sum(exit_trade['quantity'] for exit_trade in self.exits)

    def get_remaining_quantity(self) -> int:
        """Calculate remaining open quantity"""
        return self.get_total_entry_quantity() - self.get_total_exit_quantity()

    def get_average_entry_price(self) -> float:
        """Calculate weighted average entry price"""
        if not self.entries:
            return 0.0

        total_cost = sum(entry['price'] * entry['quantity'] for entry in self.entries)
        total_quantity = self.get_total_entry_quantity()

        if total_quantity == 0:
            return 0.0

        return total_cost / total_quantity

    def get_total_invested(self) -> float:
        """Calculate total capital invested (entries - exits)"""
        entry_cost = sum(entry['price'] * entry['quantity'] for entry in self.entries)
        exit_revenue = sum(exit_trade['price'] * exit_trade['quantity'] for exit_trade in self.exits)
        return entry_cost - exit_revenue

    def to_dict(self) -> Dict[str, Any]:
        """Convert Position to dictionary for JSON serialization"""
        return {
            'code': self.code,
            'name': self.name,
            'state': self.state.value,
            'entries': self.entries,
            'exits': self.exits,
            'current_price': self.current_price,
            'unrealized_pnl': self.unrealized_pnl,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """Create Position from dictionary"""
        return cls(
            code=data['code'],
            name=data['name'],
            state=PositionState(data['state']),
            entries=data.get('entries', []),
            exits=data.get('exits', []),
            current_price=data.get('current_price', 0.0),
            unrealized_pnl=data.get('unrealized_pnl', 0.0),
            created_at=data.get('created_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            updated_at=data.get('updated_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )


class BNFPositionManager:
    """
    Manages BNF trading positions with multi-day tracking and risk controls.

    Features:
    - Multi-day position tracking
    - Position state management
    - JSON persistence
    - Risk management checks
    - P&L calculation
    """

    def __init__(self, data_dir: str = "data/bnf", total_capital: float = 10000000.0):
        """
        Initialize BNF Position Manager

        Args:
            data_dir: Directory for storing position data
            total_capital: Total trading capital for risk calculations
        """
        self.data_dir = Path(data_dir)
        self.positions_file = self.data_dir / "positions.json"
        self.total_capital = total_capital
        self.positions: Dict[str, Position] = {}

        # Risk management parameters
        self.max_positions = 5
        self.max_position_ratio = 0.20  # 20% per position

        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Load existing positions
        self.load_positions()

    def add_position(
        self,
        code: str,
        name: str,
        state: PositionState = PositionState.PENDING
    ) -> Optional[Position]:
        """
        Add a new position

        Args:
            code: Stock code
            name: Stock name
            state: Initial position state

        Returns:
            Created Position or None if cannot add
        """
        # Check if position already exists
        if code in self.positions:
            print(f"Position for {code} already exists")
            return None

        # Check if can add new position
        if not self.can_add_position():
            print(f"Cannot add position: Max positions ({self.max_positions}) reached")
            return None

        # Create new position
        position = Position(
            code=code,
            name=name,
            state=state
        )

        self.positions[code] = position
        self.save_positions()

        return position

    def update_position(
        self,
        code: str,
        current_price: Optional[float] = None,
        state: Optional[PositionState] = None
    ) -> Optional[Position]:
        """
        Update position details

        Args:
            code: Stock code
            current_price: Updated current price
            state: Updated state

        Returns:
            Updated Position or None if not found
        """
        if code not in self.positions:
            print(f"Position {code} not found")
            return None

        position = self.positions[code]

        if current_price is not None:
            position.current_price = current_price
            position.unrealized_pnl = self.calculate_pnl(position)

        if state is not None:
            position.state = state

        position.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.save_positions()

        return position

    def partial_entry(
        self,
        code: str,
        price: float,
        quantity: int,
        date: Optional[str] = None,
        time: Optional[str] = None
    ) -> Optional[Position]:
        """
        Record a partial entry (split entry)

        Args:
            code: Stock code
            price: Entry price
            quantity: Entry quantity
            date: Entry date (YYYY-MM-DD)
            time: Entry time (HH:MM:SS)

        Returns:
            Updated Position or None if not found
        """
        if code not in self.positions:
            print(f"Position {code} not found")
            return None

        position = self.positions[code]

        # Set timestamps
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        if time is None:
            time = datetime.now().strftime("%H:%M:%S")

        # Add entry
        entry = {
            'price': price,
            'quantity': quantity,
            'date': date,
            'time': time
        }
        position.entries.append(entry)

        # Update state
        if position.state == PositionState.PENDING:
            position.state = PositionState.PARTIAL

        position.current_price = price
        position.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.save_positions()

        return position

    def complete_entry(self, code: str) -> Optional[Position]:
        """
        Mark position as fully entered

        Args:
            code: Stock code

        Returns:
            Updated Position or None if not found
        """
        if code not in self.positions:
            print(f"Position {code} not found")
            return None

        position = self.positions[code]
        position.state = PositionState.FULL
        position.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.save_positions()

        return position

    def partial_exit(
        self,
        code: str,
        price: float,
        quantity: int,
        date: Optional[str] = None,
        time: Optional[str] = None
    ) -> Optional[Position]:
        """
        Record a partial exit (split exit)

        Args:
            code: Stock code
            price: Exit price
            quantity: Exit quantity
            date: Exit date (YYYY-MM-DD)
            time: Exit time (HH:MM:SS)

        Returns:
            Updated Position or None if not found
        """
        if code not in self.positions:
            print(f"Position {code} not found")
            return None

        position = self.positions[code]

        # Check if enough quantity to exit
        remaining = position.get_remaining_quantity()
        if quantity > remaining:
            print(f"Cannot exit {quantity} shares, only {remaining} remaining")
            return None

        # Set timestamps
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        if time is None:
            time = datetime.now().strftime("%H:%M:%S")

        # Add exit
        exit_trade = {
            'price': price,
            'quantity': quantity,
            'date': date,
            'time': time
        }
        position.exits.append(exit_trade)

        # Update state
        if position.state == PositionState.FULL:
            position.state = PositionState.EXITING

        position.current_price = price
        position.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.save_positions()

        return position

    def close_position(self, code: str) -> Optional[Position]:
        """
        Mark position as fully closed

        Args:
            code: Stock code

        Returns:
            Closed Position or None if not found
        """
        if code not in self.positions:
            print(f"Position {code} not found")
            return None

        position = self.positions[code]

        # Verify all quantity is exited
        remaining = position.get_remaining_quantity()
        if remaining > 0:
            print(f"Cannot close position: {remaining} shares still open")
            return None

        position.state = PositionState.CLOSED
        position.unrealized_pnl = 0.0  # No unrealized P&L when closed
        position.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.save_positions()

        return position

    def get_position(self, code: str) -> Optional[Position]:
        """
        Get position by code

        Args:
            code: Stock code

        Returns:
            Position or None if not found
        """
        return self.positions.get(code)

    def get_open_positions(self) -> List[Position]:
        """
        Get all open positions (not closed)

        Returns:
            List of open positions
        """
        return [
            pos for pos in self.positions.values()
            if pos.state != PositionState.CLOSED
        ]

    def get_all_positions(self) -> List[Position]:
        """
        Get all positions including closed ones

        Returns:
            List of all positions
        """
        return list(self.positions.values())

    def get_total_exposure(self) -> float:
        """
        Calculate total capital exposure across all open positions

        Returns:
            Total invested capital
        """
        total = 0.0
        for position in self.get_open_positions():
            total += position.get_total_invested()
        return total

    def can_add_position(self) -> bool:
        """
        Check if can add a new position based on risk limits

        Returns:
            True if can add position, False otherwise
        """
        open_positions = self.get_open_positions()
        return len(open_positions) < self.max_positions

    def can_enter_position(self, code: str, capital: float) -> bool:
        """
        Check if can enter position with given capital

        Args:
            code: Stock code
            capital: Capital to invest

        Returns:
            True if within risk limits, False otherwise
        """
        # Check if position exists
        if code not in self.positions:
            return False

        # Check max capital per position
        max_per_position = self.total_capital * self.max_position_ratio
        if capital > max_per_position:
            print(f"Capital {capital:,.0f} exceeds max per position {max_per_position:,.0f}")
            return False

        return True

    def calculate_pnl(self, position: Position) -> float:
        """
        Calculate unrealized P&L for a position

        Args:
            position: Position to calculate P&L for

        Returns:
            Unrealized P&L
        """
        if position.state == PositionState.CLOSED:
            return 0.0

        if position.state == PositionState.PENDING:
            return 0.0

        remaining_quantity = position.get_remaining_quantity()
        if remaining_quantity == 0:
            return 0.0

        avg_entry_price = position.get_average_entry_price()
        if avg_entry_price == 0 or position.current_price == 0:
            return 0.0

        # Calculate unrealized P&L on remaining quantity
        unrealized_pnl = (position.current_price - avg_entry_price) * remaining_quantity

        return unrealized_pnl

    def calculate_realized_pnl(self, position: Position) -> float:
        """
        Calculate realized P&L from exits

        Args:
            position: Position to calculate P&L for

        Returns:
            Realized P&L
        """
        if not position.exits:
            return 0.0

        avg_entry_price = position.get_average_entry_price()
        if avg_entry_price == 0:
            return 0.0

        # Calculate realized P&L from all exits
        realized_pnl = 0.0
        for exit_trade in position.exits:
            exit_price = exit_trade['price']
            exit_quantity = exit_trade['quantity']
            realized_pnl += (exit_price - avg_entry_price) * exit_quantity

        return realized_pnl

    def get_position_summary(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed summary of a position

        Args:
            code: Stock code

        Returns:
            Position summary dictionary or None if not found
        """
        position = self.get_position(code)
        if not position:
            return None

        return {
            'code': position.code,
            'name': position.name,
            'state': position.state.value,
            'total_entries': len(position.entries),
            'total_exits': len(position.exits),
            'entry_quantity': position.get_total_entry_quantity(),
            'exit_quantity': position.get_total_exit_quantity(),
            'remaining_quantity': position.get_remaining_quantity(),
            'avg_entry_price': position.get_average_entry_price(),
            'current_price': position.current_price,
            'total_invested': position.get_total_invested(),
            'unrealized_pnl': position.unrealized_pnl,
            'realized_pnl': self.calculate_realized_pnl(position),
            'created_at': position.created_at,
            'updated_at': position.updated_at
        }

    def save_positions(self) -> None:
        """Save positions to JSON file"""
        try:
            data = {
                'positions': {
                    code: position.to_dict()
                    for code, position in self.positions.items()
                },
                'metadata': {
                    'total_capital': self.total_capital,
                    'max_positions': self.max_positions,
                    'max_position_ratio': self.max_position_ratio,
                    'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }

            with open(self.positions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"Error saving positions: {e}")

    def load_positions(self) -> None:
        """Load positions from JSON file"""
        try:
            if not self.positions_file.exists():
                print(f"No existing positions file found at {self.positions_file}")
                return

            with open(self.positions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Load positions
            positions_data = data.get('positions', {})
            self.positions = {
                code: Position.from_dict(pos_data)
                for code, pos_data in positions_data.items()
            }

            # Load metadata if available
            metadata = data.get('metadata', {})
            if 'total_capital' in metadata:
                self.total_capital = metadata['total_capital']
            if 'max_positions' in metadata:
                self.max_positions = metadata['max_positions']
            if 'max_position_ratio' in metadata:
                self.max_position_ratio = metadata['max_position_ratio']

            print(f"Loaded {len(self.positions)} positions from {self.positions_file}")

        except Exception as e:
            print(f"Error loading positions: {e}")

    def remove_closed_positions(self) -> int:
        """
        Remove closed positions from tracking

        Returns:
            Number of positions removed
        """
        closed_codes = [
            code for code, pos in self.positions.items()
            if pos.state == PositionState.CLOSED
        ]

        for code in closed_codes:
            del self.positions[code]

        if closed_codes:
            self.save_positions()

        return len(closed_codes)

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get overall statistics

        Returns:
            Statistics dictionary
        """
        open_positions = self.get_open_positions()

        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in open_positions)
        total_exposure = self.get_total_exposure()

        return {
            'total_positions': len(self.positions),
            'open_positions': len(open_positions),
            'closed_positions': len([p for p in self.positions.values() if p.state == PositionState.CLOSED]),
            'total_exposure': total_exposure,
            'total_unrealized_pnl': total_unrealized_pnl,
            'exposure_ratio': total_exposure / self.total_capital if self.total_capital > 0 else 0,
            'available_slots': self.max_positions - len(open_positions),
            'max_positions': self.max_positions,
            'total_capital': self.total_capital
        }


if __name__ == "__main__":
    # Example usage
    print("BNF Position Manager - Example Usage\n")

    # Initialize manager
    manager = BNFPositionManager(
        data_dir="data/bnf",
        total_capital=10000000.0
    )

    # Add a new position
    print("1. Adding new position...")
    position = manager.add_position(
        code="005930",
        name="삼성전자",
        state=PositionState.PENDING
    )
    if position:
        print(f"   Added: {position.name} ({position.code}) - State: {position.state.value}")

    # Partial entry
    print("\n2. Recording partial entry...")
    position = manager.partial_entry(
        code="005930",
        price=70000,
        quantity=10
    )
    if position:
        print(f"   Entry: {position.get_total_entry_quantity()} shares @ {position.get_average_entry_price():,.0f}")

    # Another partial entry
    print("\n3. Recording another partial entry...")
    position = manager.partial_entry(
        code="005930",
        price=69000,
        quantity=5
    )
    if position:
        print(f"   Total: {position.get_total_entry_quantity()} shares @ {position.get_average_entry_price():,.0f}")

    # Complete entry
    print("\n4. Completing entry...")
    position = manager.complete_entry("005930")
    if position:
        print(f"   State: {position.state.value}")

    # Update price and calculate P&L
    print("\n5. Updating current price...")
    position = manager.update_position(
        code="005930",
        current_price=72000
    )
    if position:
        print(f"   Price: {position.current_price:,.0f}")
        print(f"   Unrealized P&L: {position.unrealized_pnl:+,.0f}")

    # Partial exit
    print("\n6. Recording partial exit...")
    position = manager.partial_exit(
        code="005930",
        price=73000,
        quantity=8
    )
    if position:
        print(f"   Exited: 8 shares @ 73,000")
        print(f"   Remaining: {position.get_remaining_quantity()} shares")
        print(f"   Realized P&L: {manager.calculate_realized_pnl(position):+,.0f}")

    # Get summary
    print("\n7. Position Summary:")
    summary = manager.get_position_summary("005930")
    if summary:
        for key, value in summary.items():
            if isinstance(value, float):
                print(f"   {key}: {value:,.2f}")
            else:
                print(f"   {key}: {value}")

    # Get statistics
    print("\n8. Overall Statistics:")
    stats = manager.get_statistics()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"   {key}: {value:,.2f}")
        else:
            print(f"   {key}: {value}")

    print("\n" + "="*60)
    print(f"Positions saved to: {manager.positions_file}")
    print("="*60)
