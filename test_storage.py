import os
import sys
import uuid
import json

# Add project root to path
sys.path.append('c:\\ExecSlate')

import database as db
from storage_service import STORAGE_ROOT

def run_test():
    # 1. Create a fake user
    print("--- Starting Storage Migration Test ---")
    email = f"test_{uuid.uuid4().hex[:6]}@example.com"
    user_id = db.create_user(email, "hash123", plan="pro")
    print(f"[+] User created: ID {user_id}")
    
    # 2. Create a project
    project_id = db.create_project(user_id, "Heavy Payload Project", "Q1 2026")
    print(f"[+] Project created: ID {project_id}")
    
    # 3. Define heavy payload
    heavy_kpi = {
        "revenue": {"value": 1000000, "growth": 15.4},
        "ebitda": {"value": 250000, "growth": 8.1},
        "roic": {"value": 18.5, "growth": 2.0}
    }
    long_revenue_series = [x * 1000 for x in range(1, 101)] * 5 # 500 items
    fake_chart_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    
    # 4. Update project (Storage backend will intercept)
    print("[+] Updating project with heavy payload...")
    db.update_project(
        project_id, user_id,
        kpi_metrics=heavy_kpi,
        revenue_series=long_revenue_series,
        revenue_chart=fake_chart_b64
    )
    
    # 5. Verify local storage files were created
    expected_kpi_file = STORAGE_ROOT / f"project_{project_id}_kpi_metrics.gz"
    expected_chart_file = STORAGE_ROOT / f"project_{project_id}_revenue_chart.gz"
    
    if expected_kpi_file.exists() and expected_chart_file.exists():
        print("[+] SUCCESS: Files successfully decopuled to .storage/")
        print(f"    - {expected_kpi_file.name} (File Size: {expected_kpi_file.stat().st_size} bytes)")
        print(f"    - {expected_chart_file.name} (File Size: {expected_chart_file.stat().st_size} bytes)")
    else:
        print("[-] FAIL: Files were not found in .storage/")
        sys.exit(1)
        
    # 6. Fetch project (Storage backend will hydrate)
    print("\n[+] Fetching project to test hydration...")
    fetched = db.get_project(project_id, user_id)
    
    # 7. Assert data is equal (not 'storage://' pointers)
    if fetched["kpi_metrics"] == heavy_kpi:
        print("[+] SUCCESS: kpi_metrics hydrated accurately from storage.")
    else:
        print("[-] FAIL: kpi_metrics mismatch.")
        print("Expected:", heavy_kpi)
        print("Got:", fetched["kpi_metrics"])
        sys.exit(1)
        
    if fetched["revenue_chart"] == fake_chart_b64:
        print("[+] SUCCESS: revenue_chart hydrated accurately from storage.")
    else:
        print("[-] FAIL: revenue_chart mismatch.")
        sys.exit(1)
        
    print("\n--- ALL TESTS PASSED! STORAGE DECOUPLING WORKS ---")

if __name__ == "__main__":
    run_test()
