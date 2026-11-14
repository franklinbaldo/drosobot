use drosobot_gateway::Gateway;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::{Arc, Mutex};
use std::thread;

fn mock_server(routes: Vec<(&'static str, &'static str)>) -> (String, Arc<Mutex<Vec<String>>>, thread::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = listener.local_addr().unwrap();
    let observed = Arc::new(Mutex::new(Vec::new()));
    let events = observed.clone();
    let handle = thread::spawn(move || {
        for (path, body) in routes {
            let (mut conn, _) = listener.accept().unwrap();
            conn.set_read_timeout(Some(std::time::Duration::from_secs(2))).unwrap();
            let mut request = [0u8; 1024];
            let n = conn.read(&mut request).unwrap();
            let line = String::from_utf8_lossy(&request[..n]).lines().next().unwrap().to_string();
            events.lock().unwrap().push(line.clone());
            assert_eq!(line, format!("GET {path} HTTP/1.1"));
            let response = format!("HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len());
            conn.write_all(response.as_bytes()).unwrap();
        }
    });
    (format!("http://{addr}"), observed, handle)
}

const INDEX: &str = "<html><title>ESP-Hi Web Control</title></html>";
const JS: &str = "function sendRequest(){}; '/control'; '/exit_calibration'; '/start_calibration'";

#[test]
fn inspect_does_not_move_robot() {
    let (url, events, handle) = mock_server(vec![("/", INDEX), ("/main.js", JS)]);
    let result = Gateway::new(&url, 2).unwrap().inspect().unwrap();
    assert!(result.esp_hi_webui_identified && result.reference_webui_protocol_match);
    assert!(result.json().contains("\"real_motor_position_measured\":false"));
    handle.join().unwrap();
    assert_eq!(events.lock().unwrap().len(), 2);
}

#[test]
fn supervised_idle_only_calls_documented_idle_route() {
    let (url, events, handle) = mock_server(vec![("/", INDEX), ("/main.js", JS), ("/exit_calibration", "{\"code\":200}")]);
    let outcome = Gateway::new(&url, 2).unwrap().request_idle(true).unwrap();
    assert!(outcome.contains("\"physical_stop_verified\":false"));
    handle.join().unwrap();
    assert_eq!(events.lock().unwrap().last().unwrap(), "GET /exit_calibration HTTP/1.1");
}

#[test]
fn invalid_protocol_blocks_idle_request() {
    let (url, events, handle) = mock_server(vec![("/", INDEX), ("/main.js", "unrelated javascript")]);
    let error = Gateway::new(&url, 2).unwrap().request_idle(true).unwrap_err();
    assert!(error.contains("blocked"));
    handle.join().unwrap();
    assert_eq!(events.lock().unwrap().len(), 2);
}
