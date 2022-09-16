use hyper::body::HttpBody;
use std::pin::Pin;
use std::task::{Context, Poll};
use tonic::codegen::StdError;
use tonic::transport::{ClientTlsConfig, Endpoint};
use tonic::{transport::Channel, Code, Status};
use utils::id::{TenantId, TenantTimelineId, TimelineId};

use proto::{
    broker_service_client::BrokerServiceClient, TenantTimelineId as ProtoTenantTimelineId,
};

// Code generated by protobuf.
pub mod proto {
    tonic::include_proto!("storage_broker");
}

pub mod metrics;

// Re-exports to avoid direct tonic dependency in user crates.
pub use tonic::Request;
pub use tonic::Streaming;

pub use hyper::Uri;

pub const DEFAULT_LISTEN_ADDR: &str = "127.0.0.1:50051";
pub const DEFAULT_ENDPOINT: &str = const_format::formatcp!("http://{DEFAULT_LISTEN_ADDR}");

// BrokerServiceClient charged with tonic provided Channel transport; helps to
// avoid depending on tonic directly in user crates.
pub type BrokerClientChannel = BrokerServiceClient<Channel>;

// Create connection object configured to run TLS if schema starts with https://
// and plain text otherwise. Connection is lazy, only endpoint sanity is
// validated here.
pub fn connect<U>(endpoint: U) -> anyhow::Result<BrokerClientChannel>
where
    U: std::convert::TryInto<Uri>,
    U::Error: std::error::Error + Send + Sync + 'static,
{
    let uri: Uri = endpoint.try_into()?;
    let mut tonic_endpoint: Endpoint = uri.into();
    // If schema starts with https, start encrypted connection; do plain text
    // otherwise.
    if let Some("https") = tonic_endpoint.uri().scheme_str() {
        let tls = ClientTlsConfig::new();
        tonic_endpoint = tonic_endpoint.tls_config(tls)?;
    }
    let channel = tonic_endpoint.connect_lazy();
    Ok(BrokerClientChannel::new(channel))
}

impl BrokerClientChannel {
    /// Create a new client to the given endpoint, but don't actually connect until the first request.
    pub async fn connect_lazy<D>(dst: D) -> Result<Self, tonic::transport::Error>
    where
        D: std::convert::TryInto<tonic::transport::Endpoint>,
        D::Error: Into<StdError>,
    {
        let conn = tonic::transport::Endpoint::new(dst)?.connect_lazy();
        Ok(Self::new(conn))
    }
}

// parse variable length bytes from protobuf
pub fn parse_proto_ttid(proto_ttid: &ProtoTenantTimelineId) -> Result<TenantTimelineId, Status> {
    let tenant_id = TenantId::from_slice(&proto_ttid.tenant_id)
        .map_err(|e| Status::new(Code::InvalidArgument, format!("malformed tenant_id: {}", e)))?;
    let timeline_id = TimelineId::from_slice(&proto_ttid.timeline_id).map_err(|e| {
        Status::new(
            Code::InvalidArgument,
            format!("malformed timeline_id: {}", e),
        )
    })?;
    Ok(TenantTimelineId {
        tenant_id,
        timeline_id,
    })
}

// These several usages don't justify anyhow dependency, though it would work as
// well.
type AnyError = Box<dyn std::error::Error + Send + Sync + 'static>;

// Provides impl HttpBody for two different types implementing it. Inspired by
// https://github.com/hyperium/tonic/blob/master/examples/src/hyper_warp/server.rs
pub enum EitherBody<A, B> {
    Left(A),
    Right(B),
}

impl<A, B> HttpBody for EitherBody<A, B>
where
    A: HttpBody + Send + Unpin,
    B: HttpBody<Data = A::Data> + Send + Unpin,
    A::Error: Into<AnyError>,
    B::Error: Into<AnyError>,
{
    type Data = A::Data;
    type Error = Box<dyn std::error::Error + Send + Sync + 'static>;

    fn is_end_stream(&self) -> bool {
        match self {
            EitherBody::Left(b) => b.is_end_stream(),
            EitherBody::Right(b) => b.is_end_stream(),
        }
    }

    fn poll_data(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
    ) -> Poll<Option<Result<Self::Data, Self::Error>>> {
        match self.get_mut() {
            EitherBody::Left(b) => Pin::new(b).poll_data(cx).map(map_option_err),
            EitherBody::Right(b) => Pin::new(b).poll_data(cx).map(map_option_err),
        }
    }

    fn poll_trailers(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
    ) -> Poll<Result<Option<hyper::HeaderMap>, Self::Error>> {
        match self.get_mut() {
            EitherBody::Left(b) => Pin::new(b).poll_trailers(cx).map_err(Into::into),
            EitherBody::Right(b) => Pin::new(b).poll_trailers(cx).map_err(Into::into),
        }
    }
}

fn map_option_err<T, U: Into<AnyError>>(err: Option<Result<T, U>>) -> Option<Result<T, AnyError>> {
    err.map(|e| e.map_err(Into::into))
}
