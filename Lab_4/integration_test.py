import requests
import time
import sys

LEADER_URL = "http://localhost:5000"
FOLLOWER_URLS = [
    "http://localhost:5001",
    "http://localhost:5002",
    "http://localhost:5003",
    "http://localhost:5004",
    "http://localhost:5005"
]

def cleanup_all_nodes():
    try:
        response = requests.post(f"{LEADER_URL}/reset", timeout=5)
        
    except Exception as e:
        print(f" Leader reset error: {e}")

    for i, follower_url in enumerate(FOLLOWER_URLS, 1):
        try:
            response = requests.post(f"{follower_url}/reset", timeout=5)
        except Exception as e:
            print(f" Follower {i} reset error: {e}")


def test_health_checks():
    print("Testing health checks...")
    
    # Check leader
    try:
        response = requests.get(f"{LEADER_URL}/health", timeout=5)
        assert response.status_code == 200
        assert response.json()["role"] == "leader"
        print(" Leader is healthy")
    except Exception as e:
        print(f" Leader health check failed: {e}")
        return False
    
    # Check all followers
    for i, follower_url in enumerate(FOLLOWER_URLS, 1):
        try:
            response = requests.get(f"{follower_url}/health", timeout=5)
            assert response.status_code == 200
            assert response.json()["role"] == "follower"
            follower_id = response.json().get("follower_id", f"follower{i}")
            print(f" {follower_id} is healthy")
        except Exception as e:
            print(f" Follower {i} health check failed: {e}")
            return False
    
    return True

def test_basic_write_and_read():
    print("\nTesting basic write and read...")
    
    # Write a key
    response = requests.post(
        f"{LEADER_URL}/write",
        json={"key": "test_key", "value": "test_value"},
        timeout=10
    )
    
    if response.status_code != 200:
        print(f" Write failed: {response.status_code} - {response.text}")
        return False
    
    print(f" Write successful: {response.json()}")
    
    # Read the key from leader
    response = requests.get(f"{LEADER_URL}/read?key=test_key", timeout=5)
    
    if response.status_code != 200:
        print(f" Read failed: {response.status_code}")
        return False
    
    data = response.json()
    if data["value"] != "test_value":
        print(f" Read returned wrong value: {data['value']}")
        return False
    
    print(f" Read successful from leader: {data}")
    
    return True

def test_follower_reads():
    print("\nTesting follower read capabilities...")
    
    # First write a test key
    test_key = "follower_read_test"
    test_value = "can_followers_read_this"
    
    response = requests.post(
        f"{LEADER_URL}/write",
        json={"key": test_key, "value": test_value},
        timeout=10
    )
    
    if response.status_code != 200:
        
        print(f" Initial write failed")
        return False
    
    # Wait a bit for replication
    time.sleep(2)
    
    # Try reading from each follower
    for i, follower_url in enumerate(FOLLOWER_URLS, 1):
        try:
            response = requests.get(f"{follower_url}/read?key={test_key}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data["value"] == test_value:
                    follower_id = data.get("follower_id", f"follower{i}")
                    print(f" {follower_id} can read data correctly")
                else:
                    print(f" Follower {i} returned wrong value: {data['value']}")
                    return False
            else:
                print(f" Follower {i} read failed: {response.status_code}")
                return False
        except Exception as e:
            print(f" Error reading from follower {i}: {e}")
            return False
    
    return True

def test_replication_propagation():
    print("\nTesting replication propagation...")
    
    # Write multiple keys
    num_keys = 100
    for i in range(num_keys):
        response = requests.post(
            f"{LEADER_URL}/write",
            json={"key": f"repl_test_{i}", "value": f"repl_value_{i}"},
            timeout=10
        )
        
        if response.status_code != 200:
            print(f" Write {i} failed")
            return False
    
    print(f" Wrote {num_keys} keys to leader")
    
    # Wait for replication
    #time.sleep(2)
    
    # Check each follower has all the keys
    for follower_url in FOLLOWER_URLS:
        try:
            response = requests.get(f"{follower_url}/dump", timeout=5)
            if response.status_code == 200:
                follower_data = response.json()
                follower_id = follower_data.get("follower_id", "unknown")
                
                # Check if all repl_test keys are present
                found_keys = 0
                for i in range(num_keys):
                    key = f"repl_test_{i}"
                    if key in follower_data["data"]:
                        if follower_data["data"][key] == f"repl_value_{i}":
                            found_keys += 1
                
                if found_keys == num_keys:
                    print(f" {follower_id} has all {num_keys} replicated keys")
                else:
                    print(f" {follower_id} only has {found_keys}/{num_keys} keys")
                    return False
            else:
                print(f" Failed to dump data from follower")
                return False
        except Exception as e:
            print(f" Error checking follower: {e}")
            return False
    
    return True

def test_multiple_writes():
    print("\nTesting multiple writes...")
    
    num_writes = 10
    for i in range(num_writes):
        response = requests.post(
            f"{LEADER_URL}/write",
            json={"key": f"key_{i}", "value": f"value_{i}"},
            timeout=10
        )
        
        if response.status_code != 200:
            print(f" Write {i} failed: {response.status_code}")
            return False
    
    print(f" All {num_writes} writes successful")
    
    # Verify all keys can be read
    for i in range(num_writes):
        response = requests.get(f"{LEADER_URL}/read?key=key_{i}", timeout=5)
        if response.status_code != 200 or response.json()["value"] != f"value_{i}":
            print(f" Read verification failed for key_{i}")
            return False
    
    print(f" All {num_writes} reads verified")
    
    return True

def test_write_updates():
    print("\nTesting write updates...")
    
    key = "update_test"
    
    # Initial write
    response = requests.post(
        f"{LEADER_URL}/write",
        json={"key": key, "value": "initial_value"},
        timeout=10
    )
    
    if response.status_code != 200:
        print(" Initial write failed")
        return False
    
    # Update the value
    response = requests.post(
        f"{LEADER_URL}/write",
        json={"key": key, "value": "updated_value"},
        timeout=10
    )
    
    if response.status_code != 200:
        print(" Update write failed")
        return False
    
    # Verify the update on leader
    response = requests.get(f"{LEADER_URL}/read?key={key}", timeout=5)
    
    if response.status_code != 200:
        print(" Read after update failed")
        return False
    
    if response.json()["value"] != "updated_value":
        print(f" Update not reflected: {response.json()['value']}")
        return False
    
    print(" Update test successful on leader")
    
    # Wait for replication
    time.sleep(1)
    
    # Verify update propagated to followers
    all_updated = True
    for follower_url in FOLLOWER_URLS:
        try:
            response = requests.get(f"{follower_url}/read?key={key}", timeout=5)
            if response.status_code == 200:
                if response.json()["value"] != "updated_value":
                    print(f" Update not replicated to a follower")
                    all_updated = False
                    break
        except:
            pass
    
    if all_updated:
        print(" Update replicated to all followers")
    
    return True

def test_data_dump():
    print("\nTesting data dump...")
    
    # Test leader dump
    response = requests.get(f"{LEADER_URL}/dump", timeout=5)
    
    if response.status_code != 200:
        print(" Leader data dump failed")
        return False
    
    leader_data = response.json()
    print(f" Leader data dump successful: {leader_data['count']} keys in store")
    print(f"  Sample data: {list(leader_data['data'].items())[:3]}")
    
    
    
    for i, follower_url in enumerate(FOLLOWER_URLS, 1):
        try:
            response = requests.get(f"{follower_url}/dump", timeout=5)
            if response.status_code == 200:
                follower_data = response.json()
                follower_id = follower_data.get("follower_id", f"follower{i}")
                print(f" {follower_id} dump successful: {follower_data['count']} keys")
            else:
                print(f" Follower {i} dump failed")
                return False
        except Exception as e:
            print(f" Error dumping follower {i}: {e}")
            return False
    
    return True

def test_consistency_check():
    print("\nTesting data consistency...")
    
    # Get leader data
    leader_response = requests.get(f"{LEADER_URL}/dump", timeout=5)
    leader_data = leader_response.json()["data"]
    
    # Check each follower
    all_consistent = True
    for i, follower_url in enumerate(FOLLOWER_URLS, 1):
        try:
            response = requests.get(f"{follower_url}/dump", timeout=5)
            if response.status_code == 200:
                follower_data = response.json()["data"]
                follower_id = response.json().get("follower_id", f"follower{i}")
                
                # Compare keys
                matching = 0
                missing = 0
                mismatched = 0
                
                for key, value in leader_data.items():
                    if key in follower_data:
                        if follower_data[key] == value:
                            matching += 1
                        else:
                            mismatched += 1
                    else:
                        missing += 1
                
                consistency_rate = (matching / len(leader_data) * 100) if leader_data else 100
                
                if consistency_rate == 100:
                    print(f" {follower_id}: 100% consistent ({matching} keys)")
                else:
                    print(f" {follower_id}: {consistency_rate:.1f}% consistent")
                    print(f"    Matching: {matching}, Missing: {missing}, Mismatched: {mismatched}")
                    all_consistent = False
        except Exception as e:
            print(f" Error checking follower {i}: {e}")
            all_consistent = False
    
    return all_consistent

def run_all_tests():
    print("=" * 60)
    print("INTEGRATION TESTS FOR KEY-VALUE STORE")
    print("=" * 60)
    
    # Wait a bit for services to be ready
    print("\nWaiting 2 seconds for services to initialize...")
    time.sleep(1)
    
    tests = [
        ("Health Checks", test_health_checks),
        ("Basic Write and Read", test_basic_write_and_read),
        ("Follower Reads", test_follower_reads),
        ("Replication Propagation", test_replication_propagation),
        ("Multiple Writes", test_multiple_writes),
        ("Write Updates", test_write_updates),
        ("Data Dump", test_data_dump),
        ("Consistency Check", test_consistency_check)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"\n {test_name} FAILED")
        except Exception as e:
            failed += 1
            print(f"\n {test_name} FAILED with exception: {e}")
    
    print("\n" + "=" * 60)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0

if __name__ == "__main__":
    try:
        success = run_all_tests()
    finally:
        cleanup_all_nodes()
    sys.exit(0 if success else 1)
