# Concurrent HTTP Server

## Overview

This project implements a concurrent (multithreaded) HTTP server with the following features:

1. **Thread Pool** - Managing concurrent requests using `ThreadPoolExecutor`
2. **Thread-safe Counter** - Tracking file access counts (with and without synchronization)
3. **Rate Limiting** - Limiting request rate per IP 

## Concurrency Concepts

### High-level definition (PLT tradition):
- **Concurrency** = language concept: constructing a program from independent parts
- **Parallelism** = hardware concept: simultaneous execution on multiple processors
- These are **orthogonal**: a concurrent program may or may not execute in parallel

### Differences from low-level definition:
- In OS tradition: Parallelism ⊂ Concurrency
- In PLT tradition: Concurrency ⊥ Parallelism (orthogonal)



## Usage

### 1. Start concurrent server (thread-safe counter)

```bash
python concurrent_server.py ./test_dir 8080
```

Optional parameters:
```bash
python concurrent_server.py ./test_dir 8080 20  # 20 threads in pool
```

### 2. Start server with naive counter (for race condition demo)

```bash
python concurrent_server.py ./test_dir 8080 10 --naive-counter
```



## Testing

### Test 1: Single-threaded vs Concurrent Comparison

Start both servers:
```bash
# Terminal 1
python server_single_threaded.py ./test_dir 8081

# Terminal 2
python concurrent_server.py ./test_dir 8080

# Terminal 3 - Run the test
python test_server.py compare 8081 8080 --requests 10
```

**Expected results**:
- Single-threaded: ~10 seconds (10 requests × 1s delay)
- Concurrent: ~1 second (all requests processed in parallel)
- **Speedup: ~10x**

### Test 2: Race Condition (Naive Counter)

```bash
# Start server with naive counter
python concurrent_server.py ./test_dir 8080 --naive-counter

# Run test
python test_server.py race 8080 --requests 100
```

**What happens**:
1. 100 threads try to increment the counter simultaneously
2. Without synchronization, a **race condition** occurs
3. The final value will be < 100 (e.g., 87, 92, etc.)

**Why race condition occurs**:
```python
# Thread 1                    # Thread 2
count = counter[file]  # 5   
                              count = counter[file]  # 5
count += 1  # 6
                              count += 1  # 6
counter[file] = 6
                              counter[file] = 6  # Lost increment!
```

### Test 3: Thread-safe Counter (With Lock)

```bash
# Start server with safe counter (default)
python concurrent_server.py ./test_dir 8080

# Run test
python test_server.py race 8080 --requests 100
```

**Expected result**:
- Counter value will be exactly **100**
- The lock ensures exclusive access: `with counter_lock:`

### Test 4: Rate Limiting

```bash
# Start server
python concurrent_server.py ./test_dir 8080

# Test 1: Spam (above limit)
python test_server.py ratelimit 8080 --duration 5 --rate 10

# Test 2: Below limit (simulates normal user)
python test_server.py ratelimit 8080 --duration 5 --rate 4
```

**Rate limiting mechanism**:
- Each IP can make maximum **5 requests/second**
- Uses `deque` to store timestamps of recent requests
- Old requests (> 1s) are automatically removed
- If there are already 5 requests in the last second → **429 Too Many Requests**

**Thread-safety**:
```python
with rate_limit_lock:
    # Access to rate_limit_data is protected
    request_times = rate_limit_data[client_ip]
    # ...
```

## Implemented Features

### 1. Thread Pool (concurrent.futures.ThreadPoolExecutor)

```python
with ThreadPoolExecutor(max_workers=10) as executor:
    while True:
        client_conn, client_addr = server_socket.accept()
        executor.submit(handle_request, client_conn, served_dir, 
                       client_addr, use_safe_counter)
```

**Advantages**:
- Limits the number of threads (doesn't create infinite threads)
- Reuses threads (thread pool pattern)
- Automatically manages thread lifecycle

### 2. Counter with synchronization

**Naive (race condition)**:
```python
def increment_counter_naive(file_path):
    current_count = file_access_counter[file_path]
    time.sleep(0.001)  # Forces interlacing
    file_access_counter[file_path] = current_count + 1
```

**Thread-safe (with Lock)**:
```python
def increment_counter_safe(file_path):
    with counter_lock:
        file_access_counter[file_path] += 1
```

### 3. Rate Limiting per IP

```python
def check_rate_limit(client_ip):
    with rate_limit_lock:
        current_time = time.time()
        request_times = rate_limit_data[client_ip]
        
        # Clean old requests
        while request_times and current_time - request_times[0] > RATE_WINDOW:
            request_times.popleft()
        
        # Check limit
        if len(request_times) >= RATE_LIMIT:
            return False
        
        request_times.append(current_time)
        return True
```

**Algorithm**:
1. For each IP, we maintain a queue (deque) with timestamps
2. For each new request:
   - Remove requests > 1 second old
   - Check if there are < 5 requests in the last interval
   - Add current timestamp if allowed

## Lab Demonstrations

### Demo 1: Race Condition vs Thread-safe

1. **Show race condition**:
   ```bash
   python concurrent_server.py ./test_dir 8080 --naive-counter
   python test_server.py race 8080 --requests 100
   ```

2. **Show fix with lock**:
   ```bash
   python concurrent_server.py ./test_dir 8080
   python test_server.py race 8080 --requests 100
   ```

### Demo 2: Rate Limiting

1. **Simulate spam**:
   ```bash
   # Terminal 1: Friend spamming (10 req/s)
   python test_server.py ratelimit 8080 --duration 10 --rate 10
   ```
   
2. **Simulate normal user** (in another terminal):
   ```bash
   # Terminal 2: Normal user (4 req/s, below limit)
   python test_server.py ratelimit 8080 --duration 10 --rate 4
   ```

**Comparative results**:
- Spam (10 req/s): ~50% rate limited (only ~5 req/s pass)
- Normal (4 req/s): ~0% rate limited (all pass)

### Demo 3: Performance Comparison

1. **With 1s delay** (uncomment `time.sleep(1)` in code):
   ```bash
   python test_server.py compare 8081 8080 --requests 10
   ```
   - Single-threaded: ~10s
   - Concurrent: ~1s
   - **Speedup: 10x**

2. **Without delay** (comment `time.sleep(1)`):
   ```bash
   python test_server.py compare 8081 8080 --requests 100
   ```
   - The difference will be smaller, but still observable
   - Concurrent is faster due to I/O overhead

## Synchronization Mechanisms Used

### 1. Threading.Lock (Mutex)

```python
counter_lock = Lock()

with counter_lock:
    # Critical section - only one thread at a time
    file_access_counter[file_path] += 1
```

**Properties**:
- **Mutual exclusion**: Only one thread can hold the lock
- **Atomicity**: Operations in the critical section are atomic
- Prevents **race conditions**

### 2. collections.defaultdict (Thread-safe at operation level)

```python
file_access_counter = defaultdict(int)
```

**Important**: 
- `defaultdict` is thread-safe for individual operations
- **BUT** the read-modify-write operation is NOT atomic:
  ```python
  counter[key] += 1  # Equivalent to: temp = counter[key]; temp += 1; counter[key] = temp
  ```
- That's why we need an explicit lock

### 3. collections.deque (Thread-safe for append/pop)

```python
rate_limit_data = defaultdict(lambda: deque())

with rate_limit_lock:
    request_times.popleft()  # Thread-safe individually, but we protect anyway
    request_times.append(current_time)
```

## Conclusion

This lab demonstrates the fundamental concepts of concurrent programming through a practical HTTP server implementation. The key takeaways are:

1. **Concurrency vs Parallelism**: Understanding that concurrency is about program structure (independent components), while parallelism is about execution (simultaneous processing). These concepts are orthogonal in the high-level (PLT) tradition.

2. **Race Conditions**: We demonstrated how unsynchronized access to shared state leads to incorrect results. The file access counter showed lost increments when multiple threads accessed it without proper locking.

3. **Synchronization Primitives**: The use of `Lock` (mutex) effectively solves race conditions by ensuring mutual exclusion in critical sections. This transforms non-atomic operations into atomic ones.

4. **Performance Benefits**: With I/O-bound operations (simulated by `time.sleep(1)`), the concurrent server achieved approximately 10x speedup compared to the single-threaded version, processing 10 requests in ~1 second versus ~10 seconds.

5. **Thread Pool Pattern**: Using `ThreadPoolExecutor` provides efficient thread management by limiting and reusing threads, preventing resource exhaustion from unbounded thread creation.

6. **Rate Limiting**: Implementing thread-safe rate limiting demonstrates practical application of synchronization in real-world scenarios, protecting the server from denial-of-service attacks while maintaining fairness.

The implementation shows that concurrent programming requires careful consideration of shared state and proper synchronization mechanisms. While concurrency adds complexity, it provides significant performance improvements for I/O-bound applications and enables better resource utilization in modern multi-core systems.