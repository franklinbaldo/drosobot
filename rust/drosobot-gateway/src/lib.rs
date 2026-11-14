//! Fail-closed, dependency-free ESP-Hi WebUI HTTP transport.
//!
//! The only actuator-related request is `GET /exit_calibration`, guarded by a
//! local supervision confirmation and a successful device/protocol check.
//! It requests DOG_STATE_IDLE, which is **not** an emergency stop and can move
//! the legs to a neutral posture. No movement commands are implemented.

use std::io::{Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

const MAX_RESPONSE_BYTES: usize = 128 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Endpoint {
    pub host: String,
    pub port: u16,
}

impl Endpoint {
    pub fn parse(url: &str) -> Result<Self, String> {
        let authority = url
            .strip_prefix("http://")
            .ok_or("Only http://host[:port] URLs are supported")?
            .trim_end_matches('/');
        if authority.is_empty()
            || authority.contains(['/', '?', '#', '@', '[', ']', '\\', ' '])
            || authority.matches(':').count() > 1
        {
            return Err("Expected plain http://host[:port] without path or credentials".into());
        }
        let (host, port) = match authority.split_once(':') {
            Some((host, port)) => (host, port.parse::<u16>().map_err(|_| "Invalid port")?),
            None => (authority, 80),
        };
        if host.is_empty()
            || host.len() > 253
            || !host
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'.' || c == b'-')
            || port == 0
        {
            return Err("Invalid host or port".into());
        }
        Ok(Self { host: host.to_string(), port })
    }
}

#[derive(Debug, PartialEq, Eq)]
pub struct Inspection {
    pub http_reachable: bool,
    pub esp_hi_webui_identified: bool,
    pub reference_webui_protocol_match: bool,
}

impl Inspection {
    pub fn json(&self) -> String {
        format!(
            concat!(
                "{{\"http_reachable\":{},\"esp_hi_webui_identified\":{},",
                "\"reference_webui_protocol_match\":{},",
                "\"idle_request_route\":{},",
                "\"real_motor_position_measured\":false,",
                "\"robot_battery_measured\":false,",
                "\"wifi_rssi_measured\":false,",
                "\"status_endpoint_available\":false}}"
            ),
            self.http_reachable,
            self.esp_hi_webui_identified,
            self.reference_webui_protocol_match,
            if self.reference_webui_protocol_match {
                "\"/exit_calibration\""
            } else {
                "null"
            }
        )
    }
}

#[derive(Debug, Clone)]
pub struct Gateway {
    pub endpoint: Endpoint,
    pub timeout: Duration,
}

impl Gateway {
    pub fn new(url: &str, timeout_secs: u64) -> Result<Self, String> {
        if timeout_secs == 0 || timeout_secs > 10 {
            return Err("Timeout must be between 1 and 10 seconds".into());
        }
        Ok(Self { endpoint: Endpoint::parse(url)?, timeout: Duration::from_secs(timeout_secs) })
    }

    pub fn inspect(&self) -> Result<Inspection, String> {
        // Static WebUI assets only: neither endpoint should move motors.
        let index = String::from_utf8_lossy(&self.get("/")?).into_owned();
        let script = String::from_utf8_lossy(&self.get("/main.js")?).into_owned();
        let lower = index.to_ascii_lowercase();
        let identified = lower.contains("esp-hi");
        let protocol = script.contains("/control")
            && script.contains("/exit_calibration")
            && script.contains("/start_calibration")
            && script.contains("sendRequest");
        Ok(Inspection {
            http_reachable: true,
            esp_hi_webui_identified: identified,
            reference_webui_protocol_match: protocol,
        })
    }

    pub fn request_idle(&self, supervised: bool) -> Result<&'static str, String> {
        // Not a physical emergency stop. This sends a POSTURE request.
        if !supervised {
            return Err("Physical supervision confirmation required".into());
        }
        let inspected = self.inspect()?;
        if !inspected.esp_hi_webui_identified || !inspected.reference_webui_protocol_match {
            return Err("ESP-Hi device/protocol not verified; idle request blocked".into());
        }
        let data = self.get("/exit_calibration")?;
        let response = String::from_utf8(data).map_err(|_| "Invalid UTF-8 response")?;
        let compact: String = response.chars().filter(|c| !c.is_ascii_whitespace()).collect();
        if compact != "{\"code\":200}" {
            return Err("Idle posture request not acknowledged by WebUI".into());
        }
        Ok(concat!(
            "{\"idle_request_acknowledged_by_webui\":true,",
            "\"physical_stop_verified\":false,",
            "\"note\":\"DOG_STATE_IDLE is a posture command, not a certified emergency stop.\"}"
        ))
    }

    fn get(&self, path: &str) -> Result<Vec<u8>, String> {
        // Path is strictly from our own internal allowlist, never a user input.
        if !matches!(path, "/" | "/main.js" | "/exit_calibration") {
            return Err("Path not allowed".into());
        }
        let target = format!("{}:{}", self.endpoint.host, self.endpoint.port);
        let addresses: Vec<_> = target.to_socket_addrs()
            .map_err(|_| "Could not resolve robot hostname")?
            .collect();
        let mut stream = addresses.iter()
            .find_map(|address| TcpStream::connect_timeout(address, self.timeout).ok())
            .ok_or("Robot TCP connection failed")?;
        stream.set_read_timeout(Some(self.timeout)).map_err(|_| "Cannot set read timeout")?;
        stream.set_write_timeout(Some(self.timeout)).map_err(|_| "Cannot set write timeout")?;
        let request = format!(
            "GET {path} HTTP/1.1\r\nHost: {}\r\nAccept: */*\r\nUser-Agent: DrosoBot/0.1\r\nConnection: close\r\n\r\n",
            self.endpoint.host
        );
        stream.write_all(request.as_bytes()).map_err(|_| "Could not write HTTP request")?;
        let mut bytes = Vec::new();
        let mut chunk = [0u8; 4096];
        loop {
            let n = stream.read(&mut chunk).map_err(|_| "Robot response failed or timed out")?;
            if n == 0 { break; }
            if bytes.len() + n > MAX_RESPONSE_BYTES {
                return Err("Robot HTTP response exceeds size limit".into());
            }
            bytes.extend_from_slice(&chunk[..n]);
        }
        parse_http(&bytes)
    }
}

fn parse_http(data: &[u8]) -> Result<Vec<u8>, String> {
    let split = data.windows(4).position(|w| w == b"\r\n\r\n")
        .ok_or("Malformed HTTP response")?;
    let header = std::str::from_utf8(&data[..split]).map_err(|_| "Invalid HTTP headers")?;
    let line = header.lines().next().ok_or("Missing HTTP status")?;
    if !line.starts_with("HTTP/1.0 200 ") && !line.starts_with("HTTP/1.1 200 ") {
        return Err(format!("Robot returned non-200 HTTP status: {}", line.split_whitespace().nth(1).unwrap_or("unknown")));
    }
    let mut length = None;
    let mut chunked = false;
    for line in header.split("\r\n").skip(1) {
        if let Some((name, value)) = line.split_once(':') {
            if name.eq_ignore_ascii_case("content-length") {
                length = Some(value.trim().parse::<usize>().map_err(|_| "Invalid Content-Length")?);
            }
            if name.eq_ignore_ascii_case("transfer-encoding") && value.to_ascii_lowercase().contains("chunked") {
                chunked = true;
            }
        }
    }
    let body = &data[split + 4..];
    if chunked { return parse_chunks(body); }
    if let Some(expected) = length {
        if body.len() != expected { return Err("Truncated or oversized HTTP body".into()); }
    }
    Ok(body.to_vec())
}

fn parse_chunks(mut data: &[u8]) -> Result<Vec<u8>, String> {
    let mut out = Vec::new();
    loop {
        let eol = data.windows(2).position(|w| w == b"\r\n")
            .ok_or("Invalid chunk size line")?;
        let hex = std::str::from_utf8(&data[..eol]).map_err(|_| "Invalid chunk size")?
            .split(';').next().ok_or("Missing chunk size")?;
        let count = usize::from_str_radix(hex.trim(), 16).map_err(|_| "Invalid chunk size hex")?;
        data = &data[eol + 2..];
        if count == 0 { break; }
        if count > MAX_RESPONSE_BYTES || out.len() + count > MAX_RESPONSE_BYTES || data.len() < count + 2 {
            return Err("Truncated/oversized chunk".into());
        }
        out.extend_from_slice(&data[..count]);
        if &data[count..count + 2] != b"\r\n" { return Err("Invalid chunk terminator".into()); }
        data = &data[count + 2..];
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn urls() {
        assert_eq!(Endpoint::parse("http://example.local:8080/").unwrap().port, 8080);
        for url in ["https://example.com", "http://user@host", "http://host/control", "http://host/?token=x", "http://", "http://host:0", "http://[::1]"] {
            assert!(Endpoint::parse(url).is_err(), "must reject {url}");
        }
    }
    #[test]
    fn response_parse() {
        assert_eq!(parse_http(b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nabc").unwrap(), b"abc");
        assert_eq!(parse_http(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n").unwrap(), b"abc");
        assert!(parse_http(b"HTTP/1.1 302 Found\r\nLocation: /control\r\n\r\n").is_err());
        assert!(parse_http(b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\nabc").is_err());
    }
    #[test]
    fn unsafe_idle_requires_supervision_before_io() {
        let g = Gateway::new("http://127.0.0.1:1", 1).unwrap();
        assert!(g.request_idle(false).unwrap_err().contains("supervision"));
    }
}
