BEGIN;

select _v.unregister_patch( '006-vanilla-tor' );

DROP TABLE vanilla_tor;

COMMIT;
