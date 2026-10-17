-- Per-node tables, as each worker's imager writes them (schema sevilleta of
-- the production database, without the time partitioning of epic_pixels)
create schema if not exists sevilleta;
create table sevilleta.epic_pixels (
    img_time timestamp not null,
    chan0 integer not null,
    pixel_coord point not null,
    pixel_lm point not null,
    pixel_values bytea not null,
    pix_offset point not null,
    source_name text not null,
    source_pix point
);
create index on sevilleta.epic_pixels (img_time, source_name, (pix_offset::text));
create table sevilleta.epic_img_metadata2 (
    session_id uuid not null,
    session_start timestamp not null,
    session_end timestamp not null,
    chan0 integer not null default 128,
    n_pol integer default 4,
    n_chan integer not null,
    chan_bw_hz integer not null,
    epic_version text not null,
    img_size point not null,
    npix_kernel integer default 25,
    int_time double precision,
    source_name text not null,
    primary key (session_id, source_name, chan0)
);
create table sevilleta.epic_daily_digest (
    source_name text not null,
    img_time timestamp not null,
    stokes_i real[],
    stokes_v real[],
    cfreq real not null
);
create index on sevilleta.epic_daily_digest (source_name, img_time);
create table sevilleta.epic_files_metadata2 (
    file_name text not null,
    chan_width double precision not null,
    nchan integer not null,
    support_size integer not null,
    gulp_len_ms double precision not null,
    image_len_ms double precision not null,
    epoch_time_s integer not null,
    grid_size integer not null,
    grid_res double precision not null,
    cfreq_mhz double precision not null,
    epic_version text not null,
    epoch_time timestamp generated always as (to_timestamp(epoch_time_s::double precision)) stored
);
