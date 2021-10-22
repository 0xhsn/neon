use std::{
    net::{TcpListener, TcpStream},
    thread,
};

use anyhow::{anyhow, bail};
use bytes::Bytes;
use serde::Deserialize;
use zenith_utils::{
    postgres_backend::{self, query_from_cstring, AuthType, PostgresBackend},
    pq_proto::{BeMessage, SINGLE_COL_ROWDESC},
};

use crate::{cplane_api::DatabaseInfo, ProxyState};

///
/// Main proxy listener loop.
///
/// Listens for connections, and launches a new handler thread for each.
///
pub fn thread_main(state: &'static ProxyState, listener: TcpListener) -> anyhow::Result<()> {
    loop {
        let (socket, peer_addr) = listener.accept()?;
        println!("accepted connection from {}", peer_addr);
        socket.set_nodelay(true).unwrap();

        thread::spawn(move || {
            if let Err(err) = mgmt_conn_main(state, socket) {
                println!("error: {}", err);
            }
        });
    }
}

pub fn mgmt_conn_main(state: &'static ProxyState, socket: TcpStream) -> anyhow::Result<()> {
    let mut conn_handler = MgmtHandler { state };
    let pgbackend = PostgresBackend::new(socket, AuthType::Trust, None, true)?;
    pgbackend.run(&mut conn_handler)
}

struct MgmtHandler {
    state: &'static ProxyState,
}
/// Serialized examples:
// {
//     "session_id": "71d6d03e6d93d99a",
//     "result": {
//         "Success": {
//             "host": "127.0.0.1",
//             "port": 5432,
//             "dbname": "stas",
//             "user": "stas",
//             "password": "mypass"
//         }
//     }
// }
// {
//     "session_id": "71d6d03e6d93d99a",
//     "result": {
//         "Failure": "oops"
//     }
// }
//
// // to test manually by sending a query to mgmt interface:
// psql -h 127.0.0.1 -p 9999 -c '{"session_id":"4f10dde522e14739","result":{"Success":{"host":"127.0.0.1","port":5432,"dbname":"stas","user":"stas","password":"stas"}}}'
#[derive(Deserialize)]
pub struct PsqlSessionResponse {
    session_id: String,
    result: PsqlSessionResult,
}

#[derive(Deserialize)]
pub enum PsqlSessionResult {
    Success(DatabaseInfo),
    Failure(String),
}

impl postgres_backend::Handler for MgmtHandler {
    fn process_query(
        &mut self,
        pgb: &mut PostgresBackend,
        query_string: Bytes,
    ) -> anyhow::Result<()> {
        let res = try_process_query(self, pgb, query_string);
        // intercept and log error message
        if res.is_err() {
            println!("Mgmt query failed: #{:?}", res);
        }
        res
    }
}

fn try_process_query(
    mgmt: &mut MgmtHandler,
    pgb: &mut PostgresBackend,
    query_string: Bytes,
) -> anyhow::Result<()> {
    let query_string = query_from_cstring(query_string);

    println!("Got mgmt query: '{}'", std::str::from_utf8(&query_string)?);

    let resp: PsqlSessionResponse = serde_json::from_slice(&query_string)?;

    let waiters = mgmt.state.waiters.lock().unwrap();

    let sender = waiters
        .get(&resp.session_id)
        .ok_or_else(|| anyhow!("psql_session_id is not found"))?;

    match resp.result {
        PsqlSessionResult::Success(db_info) => {
            sender.send(Ok(db_info))?;

            pgb.write_message_noflush(&SINGLE_COL_ROWDESC)?
                .write_message_noflush(&BeMessage::DataRow(&[Some(b"ok")]))?
                .write_message(&BeMessage::CommandComplete(b"SELECT 1"))?;

            Ok(())
        }

        PsqlSessionResult::Failure(message) => {
            sender.send(Err(anyhow!(message.clone())))?;

            bail!("psql session request failed: {}", message)
        }
    }
}
