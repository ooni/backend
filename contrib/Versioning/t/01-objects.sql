BEGIN;
    -- load pgtap - change next line to point to correct path for your system!
    \i t/00-load.sql.inc

    SELECT plan(11);

    SELECT has_schema( '_v', 'There should be schema _v for versioning to work.' );
    SELECT has_table( '_v', 'patches', 'There should be _v.patches table for versioning to work.' );

    SELECT has_column( '_v', 'patches', 'patch_name', '_v.patches should have patch_name column.' );
    SELECT has_column( '_v', 'patches', 'applied_tsz', '_v.patches should have applied_tsz column.' );
    SELECT has_column( '_v', 'patches', 'applied_by', '_v.patches should have applied_by column.' );
    SELECT has_column( '_v', 'patches', 'requires', '_v.patches should have requires column.' );
    SELECT has_column( '_v', 'patches', 'conflicts', '_v.patches should have conflicts column.' );

    SELECT has_function( '_v', 'register_patch', ARRAY[ 'text', 'text[]', 'text[]' ], 'register_patch(text, text[], text[]) should exist to be able to register patches' );
    SELECT has_function( '_v', 'register_patch', ARRAY[ 'text' ], 'register_patch(text) should exist to be able to register patches (in simpler way)' );
    SELECT has_function( '_v', 'unregister_patch', ARRAY[ 'text' ], 'unregister_patch(text) should exist to be able to unregister patches that are no longer needed' );

    SELECT is( ( SELECT count(*) FROM _v.patches ), 0::bigint, 'When running tests _v.patches table should be empty to prevent bad interactions between patches and tests.' );

ROLLBACK;

