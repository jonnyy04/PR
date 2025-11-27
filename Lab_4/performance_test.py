import requests
import time
import threading
import statistics
import matplotlib.pyplot as plt
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

LEADER_URL = "http://localhost:5000"
FOLLOWER_URLS = [
    "http://localhost:5001",
    "http://localhost:5002",
    "http://localhost:5003",
    "http://localhost:5004",
    "http://localhost:5005"
]

NUM_WRITES = 500
NUM_KEYS = 100
NUM_THREADS = 10

class PerformanceTester:
    def __init__(self):
        self.results = defaultdict(list)
        self.lock = threading.Lock()
        # Create session for connection pooling
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=100,
            pool_maxsize=100,
            max_retries=3
        )
        self.session.mount('http://', adapter)


    def cleanup_all_nodes(self):
        print("\nCleaning up leader and followers...")
        try:
            resp = self.session.post(f"{LEADER_URL}/reset", timeout=5)
            
        except Exception as e:
            print(f" Leader reset error: {e}")

        for i, follower_url in enumerate(FOLLOWER_URLS, 1):
            try:
                resp = self.session.post(f"{follower_url}/reset", timeout=5)
            except Exception as e:
                print(f" Follower {i} reset error: {e}")
    
    def write_single(self, key, value):
        start_time = time.perf_counter()
        try:
            response = self.session.post(
                f"{LEADER_URL}/write",
                json={"key": key, "value": value},
                timeout=10
            )
            elapsed = time.perf_counter() - start_time
            return {
                'latency': elapsed,
                'success': response.status_code == 200
            }
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            return {
                'latency': elapsed,
                'success': False,
                'error': str(e)
            }
    
    def run_test_for_quorum(self, write_quorum):
        print(f"\n{'='*60}")
        print(f"Testing with WRITE_QUORUM = {write_quorum}")
        print(f"{'='*60}")
        
        # Update quorum via environment variable update
        self.update_leader_quorum(write_quorum)
        
        # Wait for leader to be ready
        print("Waiting for leader to stabilize...")
        time.sleep(2)
        
        # Verify quorum was updated
        try:
            resp = self.session.get(f"{LEADER_URL}/health", timeout=5)
            if resp.status_code == 200:
                actual_quorum = resp.json().get('quorum')
                print(f"Leader reports WRITE_QUORUM = {actual_quorum}")
        except:
            pass
        
        # Clear previous results
        results = []
        
        start_time = time.perf_counter()
        
        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            # Submit all write tasks
            futures = []
            for i in range(NUM_WRITES):
                key = f"key_{i % NUM_KEYS}"
                value = f"value_{write_quorum}_{i}_{time.time()}"
                future = executor.submit(self.write_single, key, value)
                futures.append(future)
            
            # Collect results
            completed = 0
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                completed += 1
                if completed % 100 == 0:
                    print(f"  Progress: {completed}/{NUM_WRITES} writes completed")
        
        total_time = time.perf_counter() - start_time
        
        # Store results
        self.results[write_quorum] = results
        
        # Analyze results
        latencies = [r['latency'] for r in results]
        successes = sum(1 for r in results if r['success'])
        
        print(f"\nResults for WRITE_QUORUM = {write_quorum}:")
        print(f"  Total writes: {len(results)}")
        print(f"  Successful: {successes}")
        print(f"  Failed: {len(results) - successes}")
        print(f"  Average latency: {statistics.mean(latencies)*1000:.2f}ms")
        print(f"  P95 latency: {statistics.quantiles(latencies, n=20)[18]*1000:.2f}ms")
        print(f"  P99 latency: {statistics.quantiles(latencies, n=100)[98]*1000:.2f}ms")
        print(f"  Min latency: {min(latencies)*1000:.2f}ms")
        print(f"  Max latency: {max(latencies)*1000:.2f}ms")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {len(results)/total_time:.2f} writes/sec")
        
        return statistics.mean(latencies)
    
    def update_leader_quorum(self, write_quorum):
        print(f"Updating WRITE_QUORUM to {write_quorum}...")
        
        # Update docker-compose.yml
        with open('docker-compose.yml', 'r') as f:
            content = f.read()
        
        lines = content.split('\n')
        new_lines = []
        for line in lines:
            if 'WRITE_QUORUM=' in line and 'environment:' not in line:
                indent = len(line) - len(line.lstrip())
                new_lines.append(' ' * indent + f'- WRITE_QUORUM={write_quorum}')
            else:
                new_lines.append(line)
        
        with open('docker-compose.yml', 'w') as f:
            f.write('\n'.join(new_lines))
        
        # Recreate only the leader
        import subprocess
        subprocess.run(['docker-compose', 'up', '-d', '--force-recreate', '--no-deps', 'leader'], 
                      capture_output=True)
    
    def check_data_consistency(self):
        print(f"\n{'='*60}")
        print("CHECKING DATA CONSISTENCY")
        print(f"{'='*60}")
        
        # Get data from leader
        leader_response = self.session.get(f"{LEADER_URL}/dump", timeout=10)
        leader_data = leader_response.json()['data']
        
        print(f"\nLeader has {len(leader_data)} keys")
        
        consistency_results = {}
        
        for i, follower_url in enumerate(FOLLOWER_URLS, 1):
            try:
                response = self.session.get(f"{follower_url}/dump", timeout=10)
                
                if response.status_code == 200:
                    follower_data = response.json()['data']
                    follower_id = response.json().get('follower_id', f'follower{i}')
                    
                    # Compare data
                    matching_keys = 0
                    mismatched_keys = 0
                    missing_keys = 0
                    
                    for key, value in leader_data.items():
                        if key in follower_data:
                            if follower_data[key] == value:
                                matching_keys += 1
                            else:
                                mismatched_keys += 1
                        else:
                            missing_keys += 1
                    
                    extra_keys = len(follower_data) - matching_keys - mismatched_keys
                    
                    consistency_results[follower_id] = {
                        'total_keys': len(follower_data),
                        'matching': matching_keys,
                        'mismatched': mismatched_keys,
                        'missing': missing_keys,
                        'extra': extra_keys,
                        'consistency_rate': matching_keys / len(leader_data) if leader_data else 1.0
                    }
                    
                    print(f"\n{follower_id}:")
                    print(f"  Total keys: {len(follower_data)}")
                    print(f"  Matching: {matching_keys}")
                    print(f"  Mismatched: {mismatched_keys}")
                    print(f"  Missing: {missing_keys}")
                    print(f"  Extra: {extra_keys}")
                    print(f"  Consistency rate: {consistency_results[follower_id]['consistency_rate']*100:.2f}%")
                else:
                    print(f"\nfollower{i}: Failed to fetch data (status {response.status_code})")
                    consistency_results[f'follower{i}'] = None
            except Exception as e:
                print(f"\nfollower{i}: Error - {e}")
                consistency_results[f'follower{i}'] = None
        
        return consistency_results
    
    def plot_results(self, quorum_latencies):
        print(f"\n{'='*60}")
        print("GENERATING PLOTS")
        print(f"{'='*60}")
        
        quorums = sorted(quorum_latencies.keys())
        latencies_ms = [quorum_latencies[q] * 1000 for q in quorums]  # Convert to ms
        
        plt.figure(figsize=(12, 7))
        plt.plot(quorums, latencies_ms, marker='o', linewidth=2, markersize=10, color='#2E86AB')
        plt.xlabel('Write Quorum', fontsize=14, fontweight='bold')
        plt.ylabel('Average Latency (milliseconds)', fontsize=14, fontweight='bold')
        plt.title('Write Quorum vs Average Write Latency\n(Semi-Synchronous Replication)', 
                 fontsize=16, fontweight='bold', pad=20)
        plt.grid(True, alpha=0.3, linestyle='--')
        plt.xticks(quorums, fontsize=12)
        plt.yticks(fontsize=12)
        
        # Add value labels on points
        for q, l in zip(quorums, latencies_ms):
            plt.text(q, l + 0.1, f'{l:.2f}ms', ha='center', va='bottom', 
                    fontsize=10, fontweight='bold')
        
        # Add shaded background regions
        plt.axhspan(min(latencies_ms), max(latencies_ms), alpha=0.1, color='gray')
        
        plt.tight_layout()
        plt.savefig('quorum_vs_latency.png', dpi=300, bbox_inches='tight')
        print(" Plot saved as 'quorum_vs_latency.png'")
        plt.close()
        
        # Also create a bar chart for better visualization
        plt.figure(figsize=(12, 7))
        bars = plt.bar(quorums, latencies_ms, color=['#06D6A0', '#118AB2', '#073B4C', '#EF476F', '#FFD166'])
        plt.xlabel('Write Quorum', fontsize=14, fontweight='bold')
        plt.ylabel('Average Latency (milliseconds)', fontsize=14, fontweight='bold')
        plt.title('Write Quorum vs Average Write Latency (Bar Chart)\n(Semi-Synchronous Replication)', 
                 fontsize=16, fontweight='bold', pad=20)
        plt.grid(True, alpha=0.3, linestyle='--', axis='y')
        plt.xticks(quorums, fontsize=12)
        plt.yticks(fontsize=12)
        
        # Add value labels on bars
        for bar, l in zip(bars, latencies_ms):
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height,
                    f'{l:.2f}ms', ha='center', va='bottom', 
                    fontsize=11, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig('quorum_vs_latency_bar.png', dpi=300, bbox_inches='tight')
        print(" Bar chart saved as 'quorum_vs_latency_bar.png'")
        plt.close()

def main():
    print("="*60)
    print("PERFORMANCE ANALYSIS - KEY-VALUE STORE REPLICATION")
    print("="*60)
    print(f"Configuration:")
    print(f"  Total writes: {NUM_WRITES}")
    print(f"  Number of keys: {NUM_KEYS}")
    print(f"  Number of threads: {NUM_THREADS}")
    print(f"  Writes per key: ~{NUM_WRITES // NUM_KEYS}")
    
    tester = PerformanceTester()
    quorum_latencies = {}
    
    # Write quorum values (1 to 5)
    for quorum in range(1, 6):
        avg_latency = tester.run_test_for_quorum(quorum)
        quorum_latencies[quorum] = avg_latency
        
        # Small delay between tests
        time.sleep(1)
    
    # Plot results
    tester.plot_results(quorum_latencies)
    
    # Check data consistency
    print("\n" + "="*60)
    print("Waiting 1 seconds for all async replications to complete...")
    time.sleep(1)
    
    consistency_results = tester.check_data_consistency()
    
    # Print comprehensive analysis
    print("\n" + "="*60)
    print("COMPREHENSIVE ANALYSIS")
    print("="*60)
    
    print("\n1. WRITE QUORUM vs LATENCY ANALYSIS:")
    print("-" * 60)
    print("\nMeasured latencies:")
    for q in sorted(quorum_latencies.keys()):
        print(f"  Quorum {q}: {quorum_latencies[q]*1000:.2f}ms")
    
    # Calculate percentage increases
    base_latency = quorum_latencies[1]
    print(f"\nLatency increase relative to Quorum=1:")
    for q in range(2, 6):
        increase = ((quorum_latencies[q] - base_latency) / base_latency) * 100
        print(f"  Quorum {q}: +{increase:.1f}%")
    
    
    print("\n2. DATA CONSISTENCY ANALYSIS:")
    print("-" * 60)
    if consistency_results:
        all_consistent = all(
            r and r['consistency_rate'] == 1.0 
            for r in consistency_results.values() 
            if r is not None
        )
        
        if all_consistent:
            print(" ALL FOLLOWERS ARE 100% CONSISTENT WITH LEADER!")
            
        else:
            print(" SOME FOLLOWERS HAVE INCONSISTENT DATA")
            avg_consistency = statistics.mean(
                r['consistency_rate'] for r in consistency_results.values() if r
            ) * 100
            print(f"  Average consistency rate: {avg_consistency:.2f}%")
            
        
        # Check for any problematic followers
        for follower_id, result in consistency_results.items():
            if result and result['consistency_rate'] < 1.0:
                print(f"\n  {follower_id}: {result['consistency_rate']*100:.2f}% consistent")
                print(f"    Missing {result['missing']} keys, {result['mismatched']} mismatched")
    
    print("\n3. PERFORMANCE METRICS:")
    print("-" * 60)
    # Calculate and display throughput for each quorum
    for q in sorted(quorum_latencies.keys()):
        results = tester.results[q]
        successes = sum(1 for r in results if r['success'])
        success_rate = (successes / len(results)) * 100
        print(f"Quorum {q}: {success_rate:.1f}% success rate")
    
    print("\n" + "="*60)
    print("PERFORMANCE TEST COMPLETE")
    print("="*60)
    print("\nGenerated files:")
    print("   quorum_vs_latency.png - Line chart")
    print("   quorum_vs_latency_bar.png - Bar chart")
    tester.cleanup_all_nodes()  

if __name__ == "__main__":
    main()