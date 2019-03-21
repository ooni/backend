BEGIN;
    -- load pgtap - change next line to point to correct path for your system!
    \i t/00-load.sql.inc

    SELECT plan(13);

    SELECT is( ( SELECT count(*) FROM _v.patches ), 0::bigint, 'When running tests _v.patches table should be empty to prevent bad interactions between patches and tests.' );

    SELECT lives_ok(
        $$SELECT _v.register_patch( 'first_patch' )$$,
        'Installation of patch without dependencies AND conflicts.'
    );

    SELECT results_eq(
        'SELECT patch_name, applied_tsz, applied_by, requires, conflicts  FROM _v.patches',
        $$SELECT 'first_patch'::text as patch_name, now() as applied_tsz, current_user::TEXT as applied_by, '{}'::TEXT[] as requires, '{}'::TEXT[] as conflicts$$,
        'Sanity check if patch is correctly saved.'
    );

    SELECT lives_ok(
        $$SELECT _v.assert_patch_is_applied( 'first_patch' )$$,
        'Assert first patch is applied.'
    );

    SELECT throws_ok(
        $$SELECT _v.assert_patch_is_applied( 'bogus_patch' )$$,
        'P0001',
        'Patch bogus_patch is not applied!',
        'Raise exception when asserting a patch has been applied when it has not.'
    );

    SELECT lives_ok(
        $$SELECT _v.register_patch( 'second_patch', ARRAY[ 'first_patch' ], NULL )$$,
        'Installation of patch with dependencies.'
    );
    SELECT lives_ok(
        $$SELECT _v.register_patch( 'third_patch', ARRAY[ 'first_patch', 'second_patch' ], ARRAY[ 'bad_patch' ] )$$,
        'Installation of patch with dependencies and conflict.'
    );
    SELECT throws_matching(
        $$SELECT _v.register_patch( 'fourth_patch', ARRAY[ 'bad_patch' ], ARRAY[ 'another' ] )$$,
        'Missing prerequisite',
        'Installation of patch without meeting its requirements.'
    );
    SELECT throws_matching(
        $$SELECT _v.register_patch( 'fifth_patch', NULL, ARRAY[ 'first_patch' ] )$$,
        'Versioning patches conflict.',
        'Installation of patch with conflicting patch installed'
    );
    SELECT throws_matching(
        $$SELECT _v.register_patch( 'first_patch' )$$,
        'already applied',
        'Installation of patch that is already installed.'
    );
    SELECT throws_matching(
        $$SELECT _v.unregister_patch( 'first_patch' )$$,
        'it is required',
        'De-installation of patch that is required BY something ELSE.'
    );
    SELECT throws_matching(
        $$SELECT _v.unregister_patch( 'bad_patch' )$$,
        'is not installed',
        'De-installation of patch that is not installed'
    );
    SELECT lives_ok(
        $$SELECT _v.unregister_patch( 'third_patch' )$$,
        'De-Installation of patch.'
    );

ROLLBACK;

