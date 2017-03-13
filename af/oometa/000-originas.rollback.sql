BEGIN;

select _v.unregister_patch( '000-originas' );

drop table originas;

COMMIT;
