//!
//! Misc constants, copied from PostgreSQL headers.
//!
//! TODO: These probably should be auto-generated using bindgen,
//! rather than copied by hand. Although on the other hand, it's nice
//! to have them all here in one place, and have the ability to add
//! comments on them.
//!

//
// From pg_tablespace_d.h
//
pub const DEFAULTTABLESPACE_OID: u32 = 1663;
pub const GLOBALTABLESPACE_OID: u32 = 1664;

//
// Fork numbers, from relpath.h
//
pub const MAIN_FORKNUM: u8 = 0;
pub const FSM_FORKNUM: u8 = 1;
pub const VISIBILITYMAP_FORKNUM: u8 = 2;
pub const INIT_FORKNUM: u8 = 3;

// From storage_xlog.h
pub const SMGR_TRUNCATE_HEAP: u32 = 0x0001;
pub const SMGR_TRUNCATE_VM: u32 = 0x0002;
pub const SMGR_TRUNCATE_FSM: u32 = 0x0004;

//
// Constants from visbilitymap.h
//
pub const SIZE_OF_PAGE_HEADER: u16 = 24;
pub const BITS_PER_HEAPBLOCK: u16 = 2;
pub const HEAPBLOCKS_PER_PAGE: u16 = (BLCKSZ - SIZE_OF_PAGE_HEADER) * 8 / BITS_PER_HEAPBLOCK;

pub const TRANSACTION_STATUS_COMMITTED: u8 = 0x01;
pub const TRANSACTION_STATUS_ABORTED: u8 = 0x02;
pub const TRANSACTION_STATUS_SUB_COMMITTED: u8 = 0x03;

// From xact.h
pub const XLOG_XACT_COMMIT: u8 = 0x00;
pub const XLOG_XACT_PREPARE: u8 = 0x10;
pub const XLOG_XACT_ABORT: u8 = 0x20;

/* mask for filtering opcodes out of xl_info */
pub const XLOG_XACT_OPMASK: u8 = 0x70;
/* does this record have a 'xinfo' field or not */
pub const XLOG_XACT_HAS_INFO: u8 = 0x80;

/*
 * The following flags, stored in xinfo, determine which information is
 * contained in commit/abort records.
 */
pub const XACT_XINFO_HAS_DBINFO: u32 = 1u32 << 0;
pub const XACT_XINFO_HAS_SUBXACTS: u32 = 1u32 << 1;
pub const XACT_XINFO_HAS_RELFILENODES: u32 = 1u32 << 2;
pub const XACT_XINFO_HAS_INVALS: u32 = 1u32 << 3;
pub const XACT_XINFO_HAS_TWOPHASE: u32 = 1u32 << 4;
// pub const XACT_XINFO_HAS_ORIGIN: u32 = 1u32 << 5;
// pub const XACT_XINFO_HAS_AE_LOCKS: u32 = 1u32 << 6;
// pub const XACT_XINFO_HAS_GID: u32 = 1u32 << 7;

// From pg_control.h and rmgrlist.h
pub const XLOG_SWITCH: u8 = 0x40;
pub const XLOG_SMGR_TRUNCATE: u8 = 0x20;

// From heapam_xlog.h
pub const XLOG_HEAP_INSERT: u8 = 0x00;
pub const XLOG_HEAP_DELETE: u8 = 0x10;
pub const XLOG_HEAP_UPDATE: u8 = 0x20;
pub const XLOG_HEAP_HOT_UPDATE: u8 = 0x40;
pub const XLOG_HEAP2_VISIBLE: u8 = 0x40;
pub const XLOG_HEAP2_MULTI_INSERT: u8 = 0x50;
pub const XLH_INSERT_ALL_FROZEN_SET: u8 = (1 << 5) as u8;
pub const XLH_INSERT_ALL_VISIBLE_CLEARED: u8 = (1 << 0) as u8;
pub const XLH_UPDATE_OLD_ALL_VISIBLE_CLEARED: u8 = (1 << 0) as u8;
pub const XLH_UPDATE_NEW_ALL_VISIBLE_CLEARED: u8 = (1 << 1) as u8;
pub const XLH_DELETE_ALL_VISIBLE_CLEARED: u8 = (1 << 0) as u8;

pub const RM_XLOG_ID: u8 = 0;
pub const RM_XACT_ID: u8 = 1;
pub const RM_SMGR_ID: u8 = 2;
pub const RM_CLOG_ID: u8 = 3;
pub const RM_DBASE_ID: u8 = 4;
pub const RM_TBLSPC_ID: u8 = 5;
pub const RM_MULTIXACT_ID: u8 = 6;
pub const RM_RELMAP_ID: u8 = 7;
pub const RM_STANDBY_ID: u8 = 8;
pub const RM_HEAP2_ID: u8 = 9;
pub const RM_HEAP_ID: u8 = 10;

// from xlogreader.h
pub const XLR_INFO_MASK: u8 = 0x0F;
pub const XLR_RMGR_INFO_MASK: u8 = 0xF0;

// from dbcommands_xlog.h
pub const XLOG_DBASE_CREATE: u8 = 0x00;
pub const XLOG_DBASE_DROP: u8 = 0x10;

pub const XLOG_TBLSPC_CREATE: u8 = 0x00;
pub const XLOG_TBLSPC_DROP: u8 = 0x10;

pub const SIZEOF_XLOGRECORD: u32 = 24;

// from pg_config.h. These can be changed with configure options --with-blocksize=BLOCKSIZE and
// --with-segsize=SEGSIZE, but assume the defaults for now.
pub const BLCKSZ: u16 = 8192;
pub const RELSEG_SIZE: u32 = 1024 * 1024 * 1024 / (BLCKSZ as u32);

//
// from xlogrecord.h
//
pub const XLR_MAX_BLOCK_ID: u8 = 32;

pub const XLR_BLOCK_ID_DATA_SHORT: u8 = 255;
pub const XLR_BLOCK_ID_DATA_LONG: u8 = 254;
pub const XLR_BLOCK_ID_ORIGIN: u8 = 253;
pub const XLR_BLOCK_ID_TOPLEVEL_XID: u8 = 252;

pub const BKPBLOCK_FORK_MASK: u8 = 0x0F;
pub const _BKPBLOCK_FLAG_MASK: u8 = 0xF0;
pub const BKPBLOCK_HAS_IMAGE: u8 = 0x10; /* block data is an XLogRecordBlockImage */
pub const BKPBLOCK_HAS_DATA: u8 = 0x20;
pub const BKPBLOCK_WILL_INIT: u8 = 0x40; /* redo will re-init the page */
pub const BKPBLOCK_SAME_REL: u8 = 0x80; /* RelFileNode omitted, same as previous */

/* Information stored in bimg_info */
pub const BKPIMAGE_HAS_HOLE: u8 = 0x01; /* page image has "hole" */
pub const BKPIMAGE_IS_COMPRESSED: u8 = 0x02; /* page image is compressed */
pub const BKPIMAGE_APPLY: u8 = 0x04; /* page image should be restored during replay */

/* From transam.h */
pub const FIRST_NORMAL_TRANSACTION_ID: u32 = 3;
pub const INVALID_TRANSACTION_ID: u32 = 0;
pub const FIRST_BOOTSTRAP_OBJECT_ID: u32 = 12000;
pub const FIRST_NORMAL_OBJECT_ID: u32 = 16384;

/* FIXME: pageserver should request wal_seg_size from compute node */
pub const WAL_SEGMENT_SIZE: usize = 16 * 1024 * 1024;
