use drosobot_gateway::Gateway;
use std::env;
use std::process::ExitCode;

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let action = args.next().ok_or("Use: drosobot inspect | request-idle --supervised")?;
    let extra: Vec<String> = args.collect();
    match action.as_str() {
        "inspect" if extra.is_empty() => {},
        "request-idle" if extra == ["--supervised"] => {},
        _ => return Err("Usage: drosobot inspect | request-idle --supervised".into()),
    }
    let endpoint = env::var("DROSOBOT_URL")
        .map_err(|_| "DROSOBOT_URL must be set to http://host[:port]")?;
    let robot = Gateway::new(&endpoint, 3)?;
    if action == "inspect" {
        println!("{}", robot.inspect()?.json());
    } else {
        println!("{}", robot.request_idle(true)?);
    }
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(msg) => { eprintln!("DrosoBot error: {msg}"); ExitCode::FAILURE }
    }
}
