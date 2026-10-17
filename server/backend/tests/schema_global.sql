-- Global tables of the head-node database: the watch list and the FRB analysis
create schema if not exists sevilleta;
create table public.epic_watchdog (
    id serial primary key,
    source text not null,
    event_time timestamp not null,
    ra_deg double precision not null,
    dec_deg double precision not null,
    event_type text not null,
    t_start timestamp default current_timestamp,
    t_end timestamp,
    watch_mode text default 'continuous',
    patch_type integer default 5,
    reason text not null,
    author text not null,
    watch_status text default 'watching',
    voevent xml
);
create table sevilleta.epic_frb_band (
    event_id integer not null,
    chan0 integer not null,
    status text not null,
    note text,
    products_version integer not null,
    dmt_version integer not null,
    meta jsonb,
    host text,
    updated_at timestamp not null default (now() at time zone 'utc'),
    primary key (event_id, chan0)
);
create table sevilleta.epic_frb_products (
    event_id integer not null,
    chan0 integer not null,
    source_name text not null,
    status text not null,
    note text,
    dm real not null,
    dm_err real not null,
    t_inf timestamp not null,
    f_lo_mhz double precision not null,
    chan_bw_hz double precision not null,
    n_chan integer not null,
    dt_s double precision,
    t0_rel_s double precision,
    n_time integer,
    smear_s double precision,
    on_half_s double precision,
    coverage real,
    flagged integer[],
    z_image bytea,
    timeseries bytea,
    peak_snr real,
    peak_width_s real,
    peak_t_s real,
    version integer not null,
    created_at timestamp not null default (now() at time zone 'utc'),
    primary key (event_id, chan0)
);
create table sevilleta.epic_frb_dmt (
    event_id integer not null,
    chan0 integer not null,
    px integer not null,
    py integer not null,
    dm_lo double precision not null,
    dm_step double precision not null,
    n_dm integer not null,
    snr_dm bytea,
    map_dm_step double precision,
    map_n_dm integer,
    map_tau0 double precision,
    map_dtau double precision,
    map_n_tau integer,
    map bytea,
    peak_snr real,
    peak_dm real,
    peak_tau real,
    peak_width_s real,
    extra jsonb,
    version integer not null,
    created_at timestamp not null default (now() at time zone 'utc'),
    primary key (event_id, chan0, px, py)
);
create table sevilleta.epic_frb_analysis (
    event_id integer primary key,
    dmt_version integer not null,
    summary jsonb not null,
    notified_at timestamp,
    created_at timestamp not null default (now() at time zone 'utc')
);
