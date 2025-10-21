import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


def make_request(url, request_id):
    start_time = time.time()
    try:
        response = requests.get(url, timeout=30)
        elapsed = time.time() - start_time
        return {
            'id': request_id,
            'status': response.status_code,
            'elapsed': elapsed,
            'success': True
        }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            'id': request_id,
            'status': 'ERROR',
            'elapsed': elapsed,
            'success': False,
            'error': str(e)
        }


def test_concurrent_requests(url, num_requests=10, num_workers=10):
    print(f"\n{'='*60}")
    print(f"Testing with {num_requests} concurrent requests...")
    print(f"{'='*60}")
    
    overall_start = time.time()
    results = []
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(make_request, url, i+1) 
                   for i in range(num_requests)]
        
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = "✓" if result['success'] else "✗"
            print(f"  {status} Request {result['id']}: "
                  f"Status={result['status']}, Time={result['elapsed']:.3f}s")
    
    overall_elapsed = time.time() - overall_start
    
    successful = sum(1 for r in results if r['success'])
    failed = len(results) - successful
    avg_time = sum(r['elapsed'] for r in results) / len(results)
    
    print(f"\n{'='*60}")
    print(f"Results:")
    print(f"  Total time: {overall_elapsed:.3f}s")
    print(f"  Successful: {successful}/{num_requests}")
    print(f"  Failed: {failed}/{num_requests}")
    print(f"  Average request time: {avg_time:.3f}s")
    print(f"  Throughput: {num_requests/overall_elapsed:.2f} requests/second")
    print(f"{'='*60}\n")
    
    return overall_elapsed, results


def test_race_condition(url, num_requests=100):
    
    print(f"\n{'='*60}")
    print(f"Testing race condition with {num_requests} concurrent requests...")
    print(f"{'='*60}")
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(make_request, url, i+1) 
                   for i in range(num_requests)]
        
        for future in as_completed(futures):
            result = future.result()
    
    print(f"Completed {num_requests} requests.")
    print(f"Check the directory listing to see the access count.")
    print(f"If using naive counter, count will be less than {num_requests}")
    print(f"If using safe counter, count should be exactly {num_requests}")
    print(f"{'='*60}\n")


def test_rate_limiting(url, duration=5, requests_per_second=10):
    
    print(f"\n{'='*60}")
    print(f"Testing rate limiting...")
    print(f"Sending {requests_per_second} requests/second for {duration} seconds")
    print(f"{'='*60}")
    
    total_requests = 0
    successful_requests = 0
    rate_limited_requests = 0
    
    start_time = time.time()
    end_time = start_time + duration
    
    while time.time() < end_time:
        loop_start = time.time()
        
        with ThreadPoolExecutor(max_workers=requests_per_second) as executor:
            futures = [executor.submit(make_request, url, i) 
                      for i in range(requests_per_second)]
            
            for future in as_completed(futures):
                result = future.result()
                total_requests += 1
                
                if result['success'] and result['status'] == 200:
                    successful_requests += 1
                elif result['status'] == 429:
                    rate_limited_requests += 1
        
        elapsed = time.time() - loop_start
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
    
    total_elapsed = time.time() - start_time
    
    print(f"\n{'='*60}")
    print(f"Rate Limiting Results:")
    print(f"  Total requests: {total_requests}")
    print(f"  Successful (200): {successful_requests}")
    print(f"  Rate limited (429): {rate_limited_requests}")
    print(f"  Success rate: {successful_requests/total_requests*100:.1f}%")
    print(f"  Throughput: {successful_requests/total_elapsed:.2f} successful requests/second")
    print(f"{'='*60}\n")
    
    return successful_requests, rate_limited_requests


def compare_servers(single_threaded_port, concurrent_port, num_requests=10):
    
    print("\n" + "="*60)
    print("COMPARING SINGLE-THREADED VS CONCURRENT SERVER")
    print("="*60)
    
    url_single = f"http://localhost:{single_threaded_port}/index.html"
    print("\n1. Testing SINGLE-THREADED server:")
    time_single, _ = test_concurrent_requests(url_single, num_requests)
    
    url_concurrent = f"http://localhost:{concurrent_port}/index.html"
    print("\n2. Testing CONCURRENT server:")
    time_concurrent, _ = test_concurrent_requests(url_concurrent, num_requests)
    
    speedup = time_single / time_concurrent
    print("\n" + "="*60)
    print("COMPARISON:")
    print(f"  Single-threaded: {time_single:.3f}s")
    print(f"  Concurrent: {time_concurrent:.3f}s")
    print(f"  Speedup: {speedup:.2f}x")
    print("="*60)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print(f"  {sys.argv[0]} <test_type> <port> [options]")
        print("\nTest types:")
        print("  concurrent - Test concurrent requests")
        print("  race - Test race condition")
        print("  ratelimit - Test rate limiting")
        print("  compare - Compare single vs concurrent (requires 2 ports)")
        print("\nExamples:")
        print(f"  {sys.argv[0]} concurrent 8080 --requests 10")
        print(f"  {sys.argv[0]} race 8080 --requests 100")
        print(f"  {sys.argv[0]} ratelimit 8080 --duration 5 --rate 10")
        print(f"  {sys.argv[0]} compare 8080 8081 --requests 10")
        sys.exit(1)
    
    test_type = sys.argv[1]
    
    if test_type == "compare":
        if len(sys.argv) < 4:
            print("Error: compare requires 2 ports")
            sys.exit(1)
        
        port1 = int(sys.argv[2])
        port2 = int(sys.argv[3])
        num_requests = 10
        
        if '--requests' in sys.argv:
            idx = sys.argv.index('--requests')
            num_requests = int(sys.argv[idx + 1])
        
        compare_servers(port1, port2, num_requests)
    
    elif test_type == "concurrent":
        port = int(sys.argv[2])
        url = f"http://localhost:{port}/index.html"
        num_requests = 10
        
        if '--requests' in sys.argv:
            idx = sys.argv.index('--requests')
            num_requests = int(sys.argv[idx + 1])
        
        test_concurrent_requests(url, num_requests)
    
    elif test_type == "race":
        port = int(sys.argv[2])
        url = f"http://localhost:{port}/index.html"
        num_requests = 100
        
        if '--requests' in sys.argv:
            idx = sys.argv.index('--requests')
            num_requests = int(sys.argv[idx + 1])
        
        test_race_condition(url, num_requests)
    
    elif test_type == "ratelimit":
        port = int(sys.argv[2])
        url = f"http://localhost:{port}/index.html"
        duration = 5
        rate = 10
        
        if '--duration' in sys.argv:
            idx = sys.argv.index('--duration')
            duration = int(sys.argv[idx + 1])
        
        if '--rate' in sys.argv:
            idx = sys.argv.index('--rate')
            rate = int(sys.argv[idx + 1])
        
        test_rate_limiting(url, duration, rate)
    
    else:
        print(f"Unknown test type: {test_type}")
        sys.exit(1)