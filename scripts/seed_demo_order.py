#!/usr/bin/env python3
"""
Seed a test order for the demo with custom address parameters
"""
import uuid
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.db.base import SessionLocal
from app.engine.order_source import seed_dev_order

def main():
    # Get parameters from command line
    address = sys.argv[1] if len(sys.argv) > 1 else "2628 US Hwy 98 N"
    city = sys.argv[2] if len(sys.argv) > 2 else "Lakeland"
    state = sys.argv[3] if len(sys.argv) > 3 else "FL"
    county = sys.argv[4] if len(sys.argv) > 4 else "Polk"
    parcel_id = sys.argv[5] if len(sys.argv) > 5 else "262828612000000060"
    
    TENANT_ID = "c0000000-0000-0000-0000-000000000001"
    
    db = SessionLocal()
    try:
        o = seed_dev_order(
            db,
            tenant_id=uuid.UUID(TENANT_ID),
            address_line_1=address,
            city=city,
            state=state,
            county=county,
            parcel_id=parcel_id,
            survey_type='Location Survey',
        )
        print(f'ORDER_ID={o.id}')
    finally:
        db.close()

if __name__ == "__main__":
    main()
